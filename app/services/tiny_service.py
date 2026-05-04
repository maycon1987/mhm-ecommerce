import os
import requests


def buscar_produtos_tiny():
    token = os.getenv("TINY_TOKEN")

    if not token:
        raise Exception("TINY_TOKEN não configurado")

    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"

    params = {
        "token": token,
        "formato": "JSON"
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Erro Tiny: {response.text}")

    data = response.json()

    if "retorno" not in data:
        raise Exception("Resposta inválida do Tiny")

    produtos = data["retorno"].get("produtos", [])

    resultado = []

    for item in produtos:
        p = item["produto"]

        resultado.append({
            "nome": p.get("nome"),
            "sku": p.get("codigo"),
            "preco": p.get("preco"),
            "estoque": p.get("estoqueAtual"),
            "tiny_id": p.get("id")
        })

    return resultado
