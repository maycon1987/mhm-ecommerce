from datetime import datetime
import re
from app.services.tiny_service import buscar_produtos_tiny, obter_produto_tiny
from fastapi import FastAPI, HTTPException
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from rembg import remove
from PIL import Image
import requests
from io import BytesIO
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from typing import List, Optional
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
# CORS - LOVABLE / FRONTEND
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class ProdutoAdminRequest(BaseModel):
    nome: str
    slug: str
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    unidade_id: Optional[str] = None
    preco_varejo: Optional[float] = None
    peso: Optional[float] = None
    comprimento: Optional[float] = None
    largura: Optional[float] = None
    altura: Optional[float] = None
    imagem_url: Optional[str] = None
    video_embed: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    ativo: bool = True


class MidiaProdutoRequest(BaseModel):
    tipo: str
    url: str
    ordem: int = 0
# =========================
# FUNÇÕES AUXILIARES
# =========================
def gerar_slug(texto: str):
    if not texto:
        return "produto-sem-nome"

    texto = texto.strip().lower()  # 🔥 remove espaços no começo

    texto = re.sub(r"[áàãâä]", "a", texto)
    texto = re.sub(r"[éèêë]", "e", texto)
    texto = re.sub(r"[íìîï]", "i", texto)
    texto = re.sub(r"[óòõôö]", "o", texto)
    texto = re.sub(r"[úùûü]", "u", texto)
    texto = re.sub(r"[ç]", "c", texto)

    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = texto.strip("-")  # 🔥 remove traços no começo/fim

    return texto or "produto-sem-nome"


def to_float(valor):
    if valor is None:
        return 0.0

    if isinstance(valor, str):
        valor = valor.replace(",", ".").strip()

    try:
        return float(valor)
    except:
        return 0.0
# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def home():
    return {"status": "ok", "app": "ecommerce-api"}


@app.get("/rotas")
def listar_rotas():
    return [
        {"path": route.path, "name": route.name}
        for route in app.routes
    ]

# =========================
# TINY ERP - ADMIN
# =========================
@app.get("/admin/tiny/status")
def tiny_status():
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


# =========================
# PRODUTOS PÚBLICOS
# =========================
@app.get("/produtos")
def listar_produtos(unidade_id: str = None):
    query = supabase.table("produtos").select(
        "id, nome, slug, imagem_url, preco_varejo, peso, comprimento, largura, altura, categoria, ativo"
    ).eq("ativo", True)

    if unidade_id:
        query = query.eq("unidade_id", unidade_id)

    response = query.execute()
    return response.data


@app.get("/produto/{slug}")
def detalhe_produto(slug: str):
    produto_resp = (
        supabase
        .table("produtos")
        .select("*")
        .eq("slug", slug)
        .eq("ativo", True)
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

    midias_resp = (
        supabase
        .table("produto_midias")
        .select("*")
        .eq("produto_id", produto["id"])
        .order("ordem")
        .execute()
    )

    return {
        "produto": produto,
        "precos": precos_resp.data,
        "midias": midias_resp.data
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
    melhor_envio_url = os.getenv("MELHOR_ENVIO_URL", "https://www.melhorenvio.com.br")
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

        for campo in ["peso", "comprimento", "largura", "altura"]:
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
        "from": {"postal_code": cep_origem},
        "to": {"postal_code": cep_destino},
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


# =========================
# ADMIN - PRODUTOS
# =========================
@app.get("/admin/produtos")
def admin_listar_produtos():
    resp = supabase.table("produtos").select("*").order("nome").execute()
    return resp.data


@app.post("/admin/produtos")
def admin_criar_produto(dados: ProdutoAdminRequest):
    resp = supabase.table("produtos").insert(dados.dict()).execute()

    if not resp.data:
        raise HTTPException(status_code=400, detail="Erro ao criar produto")

    return resp.data[0]


@app.put("/admin/produtos/{produto_id}")
def admin_atualizar_produto(produto_id: str, dados: ProdutoAdminRequest):
    resp = (
        supabase
        .table("produtos")
        .update(dados.dict())
        .eq("id", produto_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    return resp.data[0]


@app.delete("/admin/produtos/{produto_id}")
def admin_desativar_produto(produto_id: str):
    resp = (
        supabase
        .table("produtos")
        .update({"ativo": False})
        .eq("id", produto_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    return {"status": "ok", "produto": resp.data[0]}


# =========================
# ADMIN - MÍDIAS
# =========================
@app.get("/admin/produtos/{produto_id}/midias")
def admin_listar_midias(produto_id: str):
    resp = (
        supabase
        .table("produto_midias")
        .select("*")
        .eq("produto_id", produto_id)
        .order("ordem")
        .execute()
    )

    return resp.data


@app.post("/admin/produtos/{produto_id}/midias")
def admin_adicionar_midia(produto_id: str, dados: MidiaProdutoRequest):
    if dados.tipo not in ["imagem", "video"]:
        raise HTTPException(status_code=400, detail="Tipo precisa ser imagem ou video")

    resp = supabase.table("produto_midias").insert({
        "produto_id": produto_id,
        "tipo": dados.tipo,
        "url": dados.url,
        "ordem": dados.ordem
    }).execute()

    if not resp.data:
        raise HTTPException(status_code=400, detail="Erro ao adicionar mídia")

    return resp.data[0]
# =========================
# TINY - SYNC PRODUTOS COMPLETO
# =========================
@app.post("/admin/tiny/sync-produtos")
def sync_produtos_tiny():
    try:
        produtos = buscar_produtos_tiny()

        criados = []
        atualizados = []
        ignorados = []

        for p in produtos:
            tiny_id = str(p.get("tiny_id") or "").strip()

            if not tiny_id:
                ignorados.append({
                    "produto": p.get("nome"),
                    "motivo": "Produto sem tiny_id"
                })
                continue

            try:
                detalhe = obter_produto_tiny(tiny_id)
            except Exception as erro_detalhe:
                ignorados.append({
                    "produto": p.get("nome"),
                    "tiny_id": tiny_id,
                    "motivo": str(erro_detalhe)
                })
                continue

            nome = detalhe.get("nome") or p.get("nome")

            dados_produto = {
                "tiny_id": tiny_id,
                "sku": detalhe.get("sku") or p.get("sku"),
                "nome": nome,
                "slug": gerar_slug(nome),
                "descricao": detalhe.get("descricao"),
                "categoria": detalhe.get("categoria"),
                "preco_varejo": to_float(detalhe.get("preco") or p.get("preco")),
                "estoque": to_float(detalhe.get("estoque") or p.get("estoque")),
                "peso": to_float(detalhe.get("peso")),
                "comprimento": to_float(detalhe.get("comprimento")),
                "largura": to_float(detalhe.get("largura")),
                "altura": to_float(detalhe.get("altura")),
                "imagem_url": detalhe.get("imagem_url"),
                "origem": "tiny",
                "ativo": True,
                "atualizado_tiny_em": datetime.utcnow().isoformat()
            }

            existe_resp = (
                supabase
                .table("produtos")
                .select("id")
                .eq("tiny_id", tiny_id)
                .limit(1)
                .execute()
            )

            if existe_resp.data:
                produto_id = existe_resp.data[0]["id"]

                resp = (
                    supabase
                    .table("produtos")
                    .update(dados_produto)
                    .eq("id", produto_id)
                    .execute()
                )

                if resp.data:
                    atualizados.append(resp.data[0])
            else:
                resp = (
                    supabase
                    .table("produtos")
                    .insert(dados_produto)
                    .execute()
                )

                if resp.data:
                    criados.append(resp.data[0])

        return {
            "status": "ok",
            "total_recebido": len(produtos),
            "total_criados": len(criados),
            "total_atualizados": len(atualizados),
            "total_ignorados": len(ignorados),
            "ignorados": ignorados[:20]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# =========================
# IMAGEM SEM FUNDO
# =========================
@app.get("/imagem-sem-fundo")
def imagem_sem_fundo(url: str):
    try:
        response = requests.get(url)

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao baixar imagem")

        input_image = Image.open(BytesIO(response.content))

        output = remove(input_image)

        buffer = BytesIO()
        output.save(buffer, format="PNG")
        buffer.seek(0)

        return StreamingResponse(buffer, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
