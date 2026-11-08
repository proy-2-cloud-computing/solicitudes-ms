import unittest

from src.common.timeutils import (
    ahora_utc,
    esta_vencido,
    parsear_iso,
    segundos_restantes,
    sumar_horas,
)


class TimeUtilsTest(unittest.TestCase):
    def test_sumar_horas(self):
        self.assertEqual(
            sumar_horas("2026-11-11T09:30:00Z", 48),
            "2026-11-13T09:30:00Z",
        )

    def test_sumar_horas_convierte_a_utc(self):
        self.assertEqual(
            sumar_horas("2026-11-11T04:30:00-05:00", 1),
            "2026-11-11T10:30:00Z",
        )

    def test_esta_vencido(self):
        self.assertTrue(
            esta_vencido("2020-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
        )
        self.assertFalse(
            esta_vencido("2099-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
        )
        self.assertFalse(esta_vencido(None))

    def test_segundos_restantes(self):
        self.assertEqual(
            segundos_restantes("2026-01-01T01:00:00Z", "2026-01-01T00:00:00Z"),
            3600,
        )

    def test_parsear_iso_invalido(self):
        self.assertIsNone(parsear_iso("no-es-fecha"))

    def test_ahora_utc_termina_en_z(self):
        valor = ahora_utc()
        self.assertTrue(valor.endswith("Z"))
        self.assertIsNotNone(parsear_iso(valor))


if __name__ == "__main__":
    unittest.main()
