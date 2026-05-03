from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from typing import List
import os
import requests

# =========================
# CONFIG SUPABASE
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# APP
# =========================
app = FastAPI(title="MHM Ecommerce API")

# =========================
# MODELOS
# =========================
class CalcularPrecoRequest(BaseModel):
    produto_id: str
    quantidade: int


class ItemFrete(BaseModel):
    produto_id: str
    quantidade: int


class CotarFreteRequest(BaseModel):
    cep_destino: str
    itens: List[ItemFrete]


# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def home():
    return {"status": "ok", "app": "ecommerce-api"}


# =========================
# LISTAR PRODUTOS
# =========================
@app.get("/produtos")
def listar_produtos(unidade_id: str = None):
    query = supabase.table("produtos").select(
        "id, nome, slug, imagem_url, preco_varejo, peso, comprimento, largura, altura"
    )

    if unidade_id:
        query = query.eq("unidade_id", unidade_id)

    response = query.execute()
    return response.data


# =========================
# DETALHE DO PRODUTO
# =========================
@app.get("/produto/{slug}")
def detalhe_produto(slug: str):
    produto_resp = (
        supabase
        .table("produtos")
        .select("*")
        .eq("slug", slug)
        .single()
        .execute()
    )

    produto = produto_resp.data

    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    precos_resp = (
        supabase
        .table("produto_precos")
        .select("*")
        .eq("produto_id", produto["id"])
        .order("quantidade_minima")
        .execute()
    )

    return {
        "produto": produto,
        "precos": precos_resp.data
    }


# =========================
# CALCULAR PREÇO AUTOMÁTICO
# =========================
@app.post("/calcular-preco")
def calcular_preco(dados: CalcularPrecoRequest):
    produto_id = dados.produto_id
    quantidade = dados.quantidade

    if quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade inválida")

    produto_resp = (
        supabase
        .table("produtos")
        .select("id, nome")
        .eq("id", produto_id)
        .single()
        .execute()
    )

    produto = produto_resp.data

    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    precos_resp = (
        supabase
        .table("produto_precos")
        .select("*")
        .eq("produto_id", produto_id)
        .lte("quantidade_minima", quantidade)
        .order("quantidade_minima", desc=True)
        .limit(1)
        .execute()
    )

    precos = precos_resp.data

    if not precos:
        raise HTTPException(status_code=404, detail="Preço não encontrado")

    preco_aplicado = precos[0]
    preco_unitario = float(preco_aplicado["preco_unitario"])
    subtotal = preco_unitario * quantidade

    return {
        "produto_id": produto_id,
        "produto": produto["nome"],
        "quantidade": quantidade,
        "preco_unitario": preco_unitario,
        "faixa_aplicada": preco_aplicado["quantidade_minima"],
        "tipo": preco_aplicado.get("tipo"),
        "subtotal": subtotal
    }


# =========================
# COTAR FRETE - MELHOR ENVIO
# =========================
@app.post("/cotar-frete")
def cotar_frete(dados: CotarFreteRequest):
    token = os.getenv("MELHOR_ENVIO_TOKEN")
    melhor_envio_url = os.getenv("MELHOR_ENVIO_URL", "https://sandbox.melhorenvio.com.br")
    cep_origem = os.getenv("CEP_ORIGEM")
    app_user_agent = os.getenv("APP_USER_AGENT", "MHM Ecommerce (mhmcaixas@gmail.com)")

    if not token:
        raise HTTPException(status_code=500, detail="MELHOR_ENVIO_TOKEN não configurado")

    if not cep_origem:
        raise HTTPException(status_code=500, detail="CEP_ORIGEM não configurado")

    cep_destino = dados.cep_destino.replace("-", "").replace(" ", "")
    cep_origem = cep_origem.replace("-", "").replace(" ", "")

    produtos_envio = []

    for item in dados.itens:
        if item.quantidade <= 0:
            raise HTTPException(status_code=400, detail="Quantidade inválida")

        produto_resp = (
            supabase
            .table("produtos")
            .select("id, nome, preco_varejo, peso, comprimento, largura, altura")
            .eq("id", item.produto_id)
            .single()
            .execute()
        )

        produto = produto_resp.data

        if not produto:
            raise HTTPException(
                status_code=404,
                detail=f"Produto não encontrado: {item.produto_id}"
            )

        campos_obrigatorios = ["peso", "comprimento", "largura", "altura"]

        for campo in campos_obrigatorios:
            if produto.get(campo) is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Produto sem {campo} cadastrado: {produto.get('nome')}"
                )

        produtos_envio.append({
            "id": produto["id"],
            "width": float(produto["largura"]),
            "height": float(produto["altura"]),
            "length": float(produto["comprimento"]),
            "weight": float(produto["peso"]),
            "insurance_value": float(produto.get("preco_varejo") or 1),
            "quantity": item.quantidade
        })

    payload = {
        "from": {
            "postal_code": cep_origem
        },
        "to": {
            "postal_code": cep_destino
        },
        "products": produtos_envio,
        "options": {
            "receipt": False,
            "own_hand": False
        }
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": app_user_agent
    }

    response = requests.post(
        f"{melhor_envio_url}/api/v2/me/shipment/calculate",
        json=payload,
        headers=headers,
        timeout=30
    )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    resultado = response.json()

    opcoes = []

    for frete in resultado:
        if frete.get("error"):
            continue

        opcoes.append({
            "id_servico": frete.get("id"),
            "transportadora": frete.get("company", {}).get("name"),
            "servico": frete.get("name"),
            "preco": float(frete.get("price", 0)),
            "prazo": frete.get("delivery_time"),
            "imagem": frete.get("company", {}).get("picture")
        })

    return {
        "cep_origem": cep_origem,
        "cep_destino": cep_destino,
        "produtos": produtos_envio,
        "opcoes": opcoes,
        "resposta_original": resultado
    }
