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

    # =========================
    # IMAGEM (CORRIGIDO)
    # =========================
    imagem_url = None
    anexos = produto.get("anexos") or []

    if isinstance(anexos, list) and len(anexos) > 0:
        primeiro = anexos[0]

        if isinstance(primeiro, dict):
            anexo = primeiro.get("anexo")

            if isinstance(anexo, dict):
                imagem_url = anexo.get("url")

    elif isinstance(anexos, dict):
        lista = anexos.get("anexo")

        if isinstance(lista, list) and len(lista) > 0:
            primeiro = lista[0]

            if isinstance(primeiro, dict):
                imagem_url = primeiro.get("url")

    if not imagem_url:
        imagem_url = produto.get("imagem") or produto.get("urlImagem")

    # =========================
    # RETORNO FINAL (DENTRO DA FUNÇÃO)
    # =========================
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
