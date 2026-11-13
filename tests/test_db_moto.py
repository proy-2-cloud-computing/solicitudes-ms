"""db.py contra DynamoDB simulado (moto): transacciones reales.

Los demas tests mockean db; este ejecuta transact_write_items de verdad, que
es donde estaba el bug de doble serializacion (TypeSerializer + resource
client) que hacia fallar POST /solicitudes y PUT /estado en AWS.

    pip install -r requirements-dev.txt
    python3 -m unittest tests.test_db_moto -v
"""

import os
import unittest

try:
    import boto3
    from moto import mock_aws
except ImportError:  # pragma: no cover
    mock_aws = None

from src.common.responses import ApiError
from tests.helpers import item_solicitud

TABLA = "itsm-solicitudes-test"


@unittest.skipIf(mock_aws is None, "moto no esta instalado")
class DbMotoTest(unittest.TestCase):
    def setUp(self):
        os.environ.update({
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "TABLE": TABLA,
        })
        self.mock = mock_aws()
        self.mock.start()
        from src.common import db

        db._recurso = None
        self.db = db
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLA,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": nombre, "AttributeType": "S"}
                for nombre in ("tenant_id", "sk", "estado_fecha")
            ],
            KeySchema=[
                {"AttributeName": "tenant_id", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "tenant_id", "KeyType": "HASH"},
                    {"AttributeName": "estado_fecha", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )
        self.tabla = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLA)

    def tearDown(self):
        self.mock.stop()

    def _crear(self, **cambios):
        item = item_solicitud(estado="en_aprobacion", requiere_aprobacion=True, **cambios)
        historial = {
            "tenant_id": item["tenant_id"],
            "sk": f"HIST#{item['sk']}#{item['creado_en']}#abc",
            "solicitud_id": item["sk"],
            "estado_anterior": "",
            "estado_nuevo": item["estado"],
            "comentario": None,  # los None no se escriben
        }
        self.db.crear_solicitud(item, historial)
        return item

    def test_crear_escribe_solicitud_e_historial_con_tipos_nativos(self):
        item = self._crear()
        guardado = self.db.obtener_solicitud("empresa-alfa", item["sk"])
        self.assertEqual(guardado["tenant_id"], "empresa-alfa")
        self.assertEqual(guardado["sla_horas"], 48)
        self.assertIs(guardado["requiere_aprobacion"], True)
        self.assertEqual(guardado["adjuntos"], [])
        historial, _ = self.db.obtener_historial("empresa-alfa", item["sk"])
        self.assertEqual(len(historial), 1)
        self.assertNotIn("comentario", historial[0])

    def test_crear_duplicado_es_409(self):
        self._crear()
        with self.assertRaises(ApiError) as error:
            self._crear()
        self.assertEqual(error.exception.status, 409)

    def test_cambiar_estado_y_bloqueo_optimista(self):
        item = self._crear()
        self.db.cambiar_estado(
            item, {"estado": "en_proceso", "asignado_a": "u-9", "comentario": "ok"}, "u-2"
        )
        guardado = self.db.obtener_solicitud("empresa-alfa", item["sk"])
        self.assertEqual(guardado["estado"], "en_proceso")
        self.assertEqual(guardado["asignado_a"], "u-9")
        self.assertTrue(guardado["estado_fecha"].startswith("en_proceso#"))
        historial, _ = self.db.obtener_historial("empresa-alfa", item["sk"])
        self.assertEqual(len(historial), 2)

        # Copia vieja (estado en_aprobacion): la condicion falla -> 409.
        with self.assertRaises(ApiError) as error:
            self.db.cambiar_estado(item, {"estado": "cancelada"}, "u-2")
        self.assertEqual(error.exception.status, 409)


class ContarPaginadoTest(unittest.TestCase):
    def test_suma_todas_las_paginas_del_count(self):
        from unittest import mock

        from src.common import db

        paginas = [
            {"Count": 2500, "LastEvaluatedKey": {"sk": "REQ#002500"}},
            {"Count": 2500, "LastEvaluatedKey": {"sk": "REQ#005000"}},
            {"Count": 1000},
        ]
        tabla_falsa = mock.Mock()
        tabla_falsa.query.side_effect = lambda **kw: paginas[len(tabla_falsa.query.call_args_list) - 1]
        with mock.patch.object(db, "tabla", return_value=tabla_falsa):
            self.assertEqual(db._contar(KeyConditionExpression="x"), 6000)
        llamadas = tabla_falsa.query.call_args_list
        self.assertEqual(len(llamadas), 3)
        self.assertEqual(llamadas[2].kwargs["ExclusiveStartKey"], {"sk": "REQ#005000"})
        self.assertTrue(all(c.kwargs["Select"] == "COUNT" for c in llamadas))


class ConflictoTest(unittest.TestCase):
    def _error(self, codigo, motivos=None):
        error = Exception()
        error.response = {"Error": {"Code": codigo}}
        if motivos is not None:
            error.response["CancellationReasons"] = [{"Code": m} for m in motivos]
        return error

    def test_solo_condicion_o_concurrencia_es_conflicto(self):
        from src.common.db import _es_conflicto

        self.assertTrue(_es_conflicto(self._error("ConditionalCheckFailedException")))
        self.assertTrue(_es_conflicto(self._error(
            "TransactionCanceledException", ["ConditionalCheckFailed", "None"])))
        self.assertTrue(_es_conflicto(self._error(
            "TransactionCanceledException", ["TransactionConflict"])))
        with self.assertLogs("src.common.db", level="ERROR"):
            self.assertFalse(_es_conflicto(self._error(
                "TransactionCanceledException", ["ValidationError", "None"])))
        self.assertFalse(_es_conflicto(self._error("AccessDeniedException")))


if __name__ == "__main__":
    unittest.main()
