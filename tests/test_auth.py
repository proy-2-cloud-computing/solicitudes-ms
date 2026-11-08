import os
import unittest

os.environ.setdefault("TABLE", "itsm-solicitudes-test")
os.environ.setdefault("TOPIC_ARN", "arn:aws:sns:us-east-1:123:solicitudes")
os.environ.setdefault("BUCKET", "bucket-test")
os.environ.setdefault("CATALOGO_URL", "http://localhost:8000")

from src.common.auth import (  # noqa: E402
    contexto,
    es_agente_o_admin,
    obtener_authorization,
    requiere_roles,
)
from src.common.responses import ApiError  # noqa: E402
from tests.helpers import evento  # noqa: E402


class AuthTest(unittest.TestCase):
    def test_contexto_basico(self):
        ctx = contexto(evento(grupos=("solicitante", "agente")))
        self.assertEqual(ctx["tenant_id"], "empresa-alfa")
        self.assertEqual(ctx["usuario_id"], "u-1")
        self.assertEqual(ctx["grupos"], {"solicitante", "agente"})

    def test_grupos_como_string(self):
        for valor in ("solicitante, agente", "[solicitante, agente]", '["solicitante", "agente"]'):
            with self.subTest(valor=valor):
                evt = evento(grupos=None)
                evt["requestContext"]["authorizer"]["claims"][
                    "cognito:groups"
                ] = valor
                ctx = contexto(evt)
                self.assertEqual(ctx["grupos"], {"solicitante", "agente"})

    def test_sin_tenant(self):
        with self.assertRaises(ApiError) as error:
            contexto(evento(tenant=None))
        self.assertEqual(error.exception.status, 401)

    def test_sin_sub(self):
        evt = evento()
        del evt["requestContext"]["authorizer"]["claims"]["sub"]
        with self.assertRaises(ApiError):
            contexto(evt)

    def test_requiere_roles(self):
        ctx = contexto(evento(grupos=("solicitante",)))
        requiere_roles(ctx, {"solicitante"})
        with self.assertRaises(ApiError) as error:
            requiere_roles(ctx, {"agente"})
        self.assertEqual(error.exception.status, 403)

    def test_es_agente_o_admin(self):
        self.assertTrue(es_agente_o_admin(contexto(evento(grupos=("agente",)))))
        self.assertFalse(
            es_agente_o_admin(contexto(evento(grupos=("solicitante",))))
        )

    def test_authorization_case_insensitive(self):
        evt = evento(authorization="Bearer abc")
        evt["headers"] = {"aUtHoRiZaTiOn": "Bearer abc"}
        self.assertEqual(obtener_authorization(evt), "Bearer abc")
        self.assertEqual(obtener_authorization({}), "")


if __name__ == "__main__":
    unittest.main()
