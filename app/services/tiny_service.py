import os
import requests


def get_tiny_token():
    token = os.getenv("TINY_TOKEN")
    if not token:
        raise Exception("TINY_TOKEN não configurado")
    return token


def buscar_produtos_tiny():
    token = get_tiny_token()

    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"

    params = {
        "token": token,
        "formato": "JSON"
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Erro Tiny pesquisa: {response.text}")

    data = response.json()

    if "retorno" not in data:
        raise Exception("Resposta inválida do Tiny")

    produtos = data["retorno"].get("produtos", [])

    resultado = []

    for item in produtos:
        p = item.get("produto", {})

        resultado.append({
            "tiny_id": p.get("id"),
            "nome": p.get("nome"),
            "sku": p.get("codigo"),
            "preco": p.get("preco"),
            "estoque": p.get("estoqueAtual")
        })

    return resultado


def obter_produto_tiny(tiny_id: str):
    token = get_tiny_token()

    url = "https://api.tiny.com.br/api2/produto.obter.php"

    params = {
        "token": token,
        "id": tiny_id,
        "formato": "JSON"
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Erro Tiny obter produto {tiny_id}: {response.text}")

    data = response.json()

    retorno = data.get("retorno", {})

    if retorno.get("status") != "OK":
        raise Exception(f"Erro Tiny produto {tiny_id}: {retorno}")

    produto = retorno.get("produto", {})

    anexos = produto.get("anexos", [])
    imagem_url = None

    if isinstance(anexos, list) and len(anexos) > 0:
        primeiro = anexos[0].get("anexo", {})
        imagem_url = primeiro.get("url")

    return {
        "tiny_id": tiny_id,
        "nome": produto.get("nome"),
        "sku": produto.get("codigo"),
        "preco": produto.get("preco"),
        "estoque": produto.get("estoqueAtual"),
        "peso": produto.get("peso_bruto") or produto.get("peso_liquido"),
        "comprimento": produto.get("comprimento"),
        "largura": produto.get("largura"),
        "altura": produto.get("altura"),
        "categoria": produto.get("categoria"),
        "ncm": produto.get("ncm"),
        "descricao": produto.get("descricao_complementar"),
        "imagem_url": imagem_url
    }
