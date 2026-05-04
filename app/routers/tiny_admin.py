from fastapi import APIRouter
import os

router = APIRouter(
    prefix="/admin/tiny",
    tags=["Admin - Tiny ERP"]
)


@router.get("/status")
def tiny_status():
    """
    Verifica se a integração com Tiny ERP está configurada.
    """

    tiny_token = os.getenv("TINY_TOKEN")

    return {
        "status": "online",
        "tiny_configurado": bool(tiny_token),
        "mensagem": (
            "Integração Tiny configurada e pronta para sincronização"
            if tiny_token
            else "TINY_TOKEN não configurado nas variáveis de ambiente"
        )
    }
