from datetime import datetime
import re
from app.services.tiny_service import buscar_produtos_tiny, obter_produto_tiny
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
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
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "mhm-admin-2024")  # Senha do painel admin

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# APP
# =========================
app = FastAPI(title="MHM Ecommerce API")

# =========================
# CORS
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
    imagem_principal: Optional[str] = None
    ativo: bool = True


class VarianteRequest(BaseModel):
    sku: Optional[str] = None
    variante: str
    preco: Optional[float] = None
    estoque: Optional[float] = None
    peso: Optional[float] = None
    largura: Optional[float] = None
    altura: Optional[float] = None
    comprimento: Optional[float] = None
    imagem: Optional[str] = None


class ProdutoComVariantesRequest(BaseModel):
    nome: str
    categoria: Optional[str] = None
    descricao: Optional[str] = None
    imagem_principal: Optional[str] = None
    ativo: bool = True
    variantes: List[VarianteRequest] = []


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
    texto = texto.strip().lower()
    texto = re.sub(r"[áàãâä]", "a", texto)
    texto = re.sub(r"[éèêë]", "e", texto)
    texto = re.sub(r"[íìîï]", "i", texto)
    texto = re.sub(r"[óòõôö]", "o", texto)
    texto = re.sub(r"[úùûü]", "u", texto)
    texto = re.sub(r"[ç]", "c", texto)
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    texto = texto.strip("-")
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


def extrair_pai_e_variante(nome: str):
    """
    Separa produto pai e variante pelo padrão ' - '
    'Caixa Papelão n04 - 25unds' → ('Caixa Papelão n04', '25unds')
    'Caixa Papelão n04' → ('Caixa Papelão n04', '1un')
    """
    nome = nome.strip()
    if " - " in nome:
        partes = nome.rsplit(" - ", 1)
        return partes[0].strip(), partes[1].strip()
    return nome, "1un"


def agrupar_por_pai(produtos: list) -> dict:
    """
    Agrupa lista de produtos pelo produto pai.
    Usa a categoria da tabela 'produtos' antiga quando o Tiny não retorna.
    Produtos sem categoria em nenhuma fonte são ignorados.
    """
    # Busca mapa nome → categoria da tabela antiga (que já tem as categorias)
    cat_map = {}
    img_map = {}
    try:
        resp = supabase.table("produtos").select("nome, categoria, imagem_url").execute()
        for row in (resp.data or []):
            nome_row = (row.get("nome") or "").strip()
            cat = (row.get("categoria") or "").strip()
            img = row.get("imagem_url")
            if nome_row and cat:
                cat_map[nome_row] = cat
            if nome_row and img:
                img_map[nome_row] = img
    except Exception:
        pass  # Se falhar, segue sem o mapa

    grupos = {}
    ignorados = []

    for p in produtos:
        nome = (p.get("nome") or "").strip()
        if not nome:
            continue

        # Tenta pegar categoria do Tiny, senão busca do mapa da tabela antiga
        categoria = (p.get("categoria") or "").strip()
        if not categoria:
            categoria = cat_map.get(nome, "")

        # Imagem: tenta do Tiny, senão do mapa antigo
        imagem_url = p.get("imagem_url") or img_map.get(nome)

        if not categoria:
            ignorados.append(nome)
            continue

        pai, variante = extrair_pai_e_variante(nome)

        # Tenta imagem do pai também
        if not imagem_url:
            imagem_url = img_map.get(nome)

        if pai not in grupos:
            # Categoria do produto pai
            cat_pai = categoria or cat_map.get(pai, "")
            img_pai = imagem_url or img_map.get(pai)
            grupos[pai] = {
                "categoria": cat_pai,
                "imagem_principal": img_pai,
                "variantes": []
            }

        if imagem_url and not grupos[pai]["imagem_principal"]:
            grupos[pai]["imagem_principal"] = imagem_url

        if not grupos[pai]["categoria"] and categoria:
            grupos[pai]["categoria"] = categoria

        grupos[pai]["variantes"].append({
            "tiny_id":    str(p.get("tiny_id") or p.get("id") or ""),
            "sku":        p.get("sku") or p.get("codigo") or "",
            "variante":   variante,
            "preco":      to_float(p.get("preco_varejo") or p.get("preco")),
            "estoque":    to_float(p.get("estoque")),
            "peso":       to_float(p.get("peso")),
            "largura":    to_float(p.get("largura")),
            "altura":     to_float(p.get("altura")),
            "comprimento": to_float(p.get("comprimento")),
            "imagem":     imagem_url,
        })

    # Remove grupos que ficaram sem categoria mesmo depois do cruzamento
    grupos_validos = {k: v for k, v in grupos.items() if v["categoria"]}
    ignorados += [k for k, v in grupos.items() if not v["categoria"]]

    return grupos_validos, ignorados


# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def home():
    return {"status": "ok", "app": "ecommerce-api"}


@app.get("/rotas")
def listar_rotas():
    return [{"path": r.path, "name": r.name} for r in app.routes]


# =========================
# TINY ERP - STATUS
# =========================
@app.get("/admin/tiny/status")
def tiny_status():
    tiny_token = os.getenv("TINY_TOKEN")
    return {
        "status": "online",
        "tiny_configurado": bool(tiny_token),
        "mensagem": (
            "Integração Tiny configurada"
            if tiny_token
            else "TINY_TOKEN não configurado"
        )
    }


# =========================
# PRODUTOS PÚBLICOS
# Lê da nova tabela 'products' com variantes embutidas
# =========================
@app.get("/produtos")
def listar_produtos(categoria: str = None, limit: int = 500):
    """
    Retorna produtos agrupados com variantes embutidas.
    Lê da tabela 'products' (nova estrutura).
    """
    try:
        query = (
            supabase.table("products")
            .select("id, nome, slug, categoria, imagem_principal, ativo")
            .eq("ativo", True)
            .order("nome")
            .limit(limit)
        )

        if categoria:
            query = query.ilike("categoria", f"%{categoria}%")

        resp = query.execute()
        produtos = resp.data or []

        resultado = []
        for prod in produtos:
            try:
                vars_resp = (
                    supabase.table("product_variants")
                    .select("id, sku, variante, preco, estoque, peso, largura, altura, comprimento, imagem")
                    .eq("product_id", prod["id"])
                    .order("preco")
                    .execute()
                )
                variantes = vars_resp.data or []
            except Exception:
                variantes = []

            precos = [v["preco"] for v in variantes if v.get("preco")]
            prod["variantes"] = variantes
            prod["preco_minimo"] = min(precos) if precos else 0
            resultado.append(prod)

        return resultado

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/produto/{slug}")
def detalhe_produto(slug: str):
    """
    Retorna produto pai + todas as variantes + imagens.
    """
    prod_resp = (
        supabase.table("products")
        .select("*")
        .eq("slug", slug)
        .eq("ativo", True)
        .single()
        .execute()
    )

    produto = prod_resp.data
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    vars_resp = (
        supabase.table("product_variants")
        .select("*")
        .eq("product_id", produto["id"])
        .order("preco")
        .execute()
    )

    imgs_resp = (
        supabase.table("product_images")
        .select("*")
        .eq("product_id", produto["id"])
        .execute()
    )

    return {
        "produto": produto,
        "variantes": vars_resp.data,
        "imagens": imgs_resp.data
    }


# =========================
# CALCULAR PREÇO
# =========================
@app.post("/calcular-preco")
def calcular_preco(dados: CalcularPrecoRequest):
    # Busca variante pelo produto_id (agora é o id da variante)
    var_resp = (
        supabase.table("product_variants")
        .select("*")
        .eq("id", dados.produto_id)
        .single()
        .execute()
    )

    variante = var_resp.data
    if not variante:
        raise HTTPException(status_code=404, detail="Variante não encontrada")

    preco_unitario = float(variante["preco"] or 0)
    subtotal = preco_unitario * dados.quantidade

    return {
        "variante_id": dados.produto_id,
        "variante": variante["variante"],
        "sku": variante["sku"],
        "quantidade": dados.quantidade,
        "preco_unitario": preco_unitario,
        "subtotal": subtotal
    }


# =========================
# COTAR FRETE
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
        # Busca variante (nova estrutura)
        var_resp = (
            supabase.table("product_variants")
            .select("*")
            .eq("id", item.produto_id)
            .single()
            .execute()
        )

        variante = var_resp.data
        if not variante:
            raise HTTPException(status_code=404, detail=f"Variante não encontrada: {item.produto_id}")

        for campo in ["peso", "comprimento", "largura", "altura"]:
            if not variante.get(campo):
                raise HTTPException(status_code=400, detail=f"Variante sem {campo}: {variante.get('sku')}")

        produtos_envio.append({
            "id": variante["id"],
            "width": float(variante["largura"]),
            "height": float(variante["altura"]),
            "length": float(variante["comprimento"]),
            "weight": float(variante["peso"]),
            "insurance_value": float(variante.get("preco") or 1),
            "quantity": item.quantidade
        })

    payload = {
        "from": {"postal_code": cep_origem},
        "to": {"postal_code": cep_destino},
        "products": produtos_envio,
        "options": {"receipt": False, "own_hand": False}
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": app_user_agent
    }

    response = requests.post(
        f"{melhor_envio_url}/api/v2/me/shipment/calculate",
        json=payload, headers=headers, timeout=30
    )

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

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

    return {"cep_origem": cep_origem, "cep_destino": cep_destino, "opcoes": opcoes}


# =========================
# ADMIN - LISTAR PRODUTOS (nova estrutura)
# =========================
@app.get("/admin/produtos")
def admin_listar_produtos():
    resp = supabase.table("products").select("*").order("nome").execute()
    return resp.data


# =========================
# ADMIN - CADASTRAR PRODUTO MANUAL COM VARIANTES
# =========================
@app.post("/admin/produtos")
def admin_criar_produto(dados: ProdutoComVariantesRequest):
    slug = gerar_slug(dados.nome)

    # Verifica se slug já existe
    existe = supabase.table("products").select("id").eq("slug", slug).execute()
    if existe.data:
        slug = f"{slug}-{datetime.utcnow().strftime('%H%M%S')}"

    prod_resp = supabase.table("products").insert({
        "nome": dados.nome,
        "slug": slug,
        "categoria": dados.categoria,
        "descricao": dados.descricao,
        "imagem_principal": dados.imagem_principal,
        "ativo": dados.ativo,
    }).execute()

    if not prod_resp.data:
        raise HTTPException(status_code=400, detail="Erro ao criar produto")

    produto_id = prod_resp.data[0]["id"]

    # Insere variantes
    variantes_criadas = []
    for v in dados.variantes:
        var_resp = supabase.table("product_variants").insert({
            "product_id": produto_id,
            "sku": v.sku,
            "variante": v.variante,
            "preco": v.preco,
            "estoque": v.estoque,
            "peso": v.peso,
            "largura": v.largura,
            "altura": v.altura,
            "comprimento": v.comprimento,
            "imagem": v.imagem,
        }).execute()
        if var_resp.data:
            variantes_criadas.append(var_resp.data[0])

    return {
        "produto": prod_resp.data[0],
        "variantes": variantes_criadas
    }


@app.put("/admin/produtos/{produto_id}")
def admin_atualizar_produto(produto_id: str, dados: ProdutoAdminRequest):
    resp = (
        supabase.table("products")
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
        supabase.table("products")
        .update({"ativo": False})
        .eq("id", produto_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return {"status": "ok", "produto": resp.data[0]}


# =========================
# ADMIN - VARIANTES
# =========================
@app.post("/admin/produtos/{produto_id}/variantes")
def admin_adicionar_variante(produto_id: str, dados: VarianteRequest):
    resp = supabase.table("product_variants").insert({
        "product_id": produto_id,
        **dados.dict()
    }).execute()
    if not resp.data:
        raise HTTPException(status_code=400, detail="Erro ao criar variante")
    return resp.data[0]


@app.put("/admin/variantes/{variante_id}")
def admin_atualizar_variante(variante_id: str, dados: VarianteRequest):
    resp = (
        supabase.table("product_variants")
        .update(dados.dict())
        .eq("id", variante_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Variante não encontrada")
    return resp.data[0]


@app.delete("/admin/variantes/{variante_id}")
def admin_deletar_variante(variante_id: str):
    resp = (
        supabase.table("product_variants")
        .delete()
        .eq("id", variante_id)
        .execute()
    )
    return {"status": "ok"}


# =========================
# SINCRONIZAR TINY → SUPABASE
# Este é o endpoint principal chamado pelo painel admin
# Agrupa variantes automaticamente pelo padrão "Produto - 25unds"
# =========================
@app.post("/admin/sincronizar")
def sincronizar_tiny():
    """
    Sincroniza todos os produtos do Tiny para o Supabase.
    - Agrupa variantes automaticamente pelo padrão "Nome - variante"
    - Salva em products + product_variants (upsert — não duplica)
    - Ignora produtos sem categoria (itens internos)
    """
    try:
        # 1. Busca todos os produtos do Tiny
        produtos_tiny = buscar_produtos_tiny()

        if not produtos_tiny:
            return {"status": "ok", "mensagem": "Nenhum produto retornado pelo Tiny"}

        # 2. Agrupa por produto pai
        grupos, ignorados = agrupar_por_pai(produtos_tiny)

        criados = 0
        atualizados = 0
        erros = []

        # 3. Salva cada grupo no Supabase
        for nome_pai, dados in grupos.items():
            try:
                slug = gerar_slug(nome_pai)

                # Upsert na tabela products
                existe_resp = (
                    supabase.table("products")
                    .select("id")
                    .eq("slug", slug)
                    .execute()
                )

                if existe_resp.data:
                    produto_id = existe_resp.data[0]["id"]
                    supabase.table("products").update({
                        "nome": nome_pai,
                        "categoria": dados["categoria"],
                        "imagem_principal": dados["imagem_principal"],
                        "ativo": True,
                    }).eq("id", produto_id).execute()
                    atualizados += 1
                else:
                    prod_resp = supabase.table("products").insert({
                        "nome": nome_pai,
                        "slug": slug,
                        "categoria": dados["categoria"],
                        "imagem_principal": dados["imagem_principal"],
                        "ativo": True,
                    }).execute()

                    if not prod_resp.data:
                        erros.append(f"Erro ao inserir: {nome_pai}")
                        continue

                    produto_id = prod_resp.data[0]["id"]
                    criados += 1

                # Upsert variantes: deleta as antigas e reinsere
                supabase.table("product_variants").delete().eq("product_id", produto_id).execute()

                for v in dados["variantes"]:
                    supabase.table("product_variants").insert({
                        "product_id": produto_id,
                        "tiny_variant_id": v["tiny_id"],
                        "sku": v["sku"],
                        "variante": v["variante"],
                        "preco": v["preco"],
                        "estoque": v["estoque"],
                        "peso": v["peso"],
                        "largura": v["largura"],
                        "altura": v["altura"],
                        "comprimento": v["comprimento"],
                        "imagem": v["imagem"],
                    }).execute()

                # Salva imagens em product_images
                supabase.table("product_images").delete().eq("product_id", produto_id).execute()
                imagens_unicas = list({v["imagem"] for v in dados["variantes"] if v["imagem"]})
                for img_url in imagens_unicas:
                    supabase.table("product_images").insert({
                        "product_id": produto_id,
                        "imagem_url": img_url,
                    }).execute()

            except Exception as e:
                erros.append(f"{nome_pai}: {str(e)}")
                continue

        return {
            "status": "ok",
            "total_recebido_tiny": len(produtos_tiny),
            "grupos_pai": len(grupos),
            "criados": criados,
            "atualizados": atualizados,
            "ignorados_sem_categoria": len(ignorados),
            "erros": erros[:10],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# SYNC ANTIGO (mantido por compatibilidade)
# =========================
@app.post("/admin/tiny/sync-produtos")
def sync_produtos_tiny_legado():
    """Redireciona para o novo endpoint de sincronização."""
    return sincronizar_tiny()


# =========================
# DEBUG - PRODUTO TINY
# =========================
@app.get("/admin/tiny/debug-produto/{tiny_id}")
def debug_produto_tiny(tiny_id: str):
    token = os.getenv("TINY_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="TINY_TOKEN não configurado")

    url = "https://api.tiny.com.br/api2/produto.obter.php"
    params = {"token": token, "id": tiny_id, "formato": "JSON"}
    response = requests.get(url, params=params, timeout=30)
    return response.json()


@app.get("/teste-obter-produto/{tiny_id}")
def teste_obter_produto(tiny_id: str):
    return obter_produto_tiny(tiny_id)
