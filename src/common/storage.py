"""Cliente S3 para adjuntos (solo firma y verifica existencia)."""

import os

_s3 = None


def _cliente():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config

        _s3 = boto3.client(
            "s3",
            config=Config(
                connect_timeout=3,
                read_timeout=3,
                retries={"max_attempts": 2},
            ),
        )
    return _s3


def bucket():
    return os.environ["BUCKET"]


def generar_url_prefirmada(key, content_type, expiracion):
    return _cliente().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket(),
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=int(expiracion),
    )


def existe_objeto(key):
    try:
        _cliente().head_object(Bucket=bucket(), Key=key)
        return True
    except Exception as error:  # boto3 no esta instalado en tests unitarios
        codigo = getattr(error, "response", {}).get("Error", {}).get("Code")
        if str(codigo) in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
