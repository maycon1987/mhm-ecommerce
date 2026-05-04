def buscar_produtos_tiny():
    token = get_tiny_token()

    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"

    todos_produtos = []
    pagina = 1

    while True:
        params = {
            "token": token,
            "formato": "JSON",
            "pagina": pagina
        }

        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            raise Exception(f"Erro Tiny pesquisa página {pagina}: {response.text}")

        data = response.json()

        retorno = data.get("retorno", {})

        if retorno.get("status") != "OK":
            raise Exception(f"Erro Tiny pesquisa página {pagina}: {retorno}")

        produtos = retorno.get("produtos", [])

        if not produtos:
            break

        for item in produtos:
            p = item.get("produto", {})

            todos_produtos.append({
                "tiny_id": p.get("id"),
                "nome": p.get("nome"),
                "sku": p.get("codigo"),
                "preco": p.get("preco"),
                "estoque": p.get("estoqueAtual")
            })

        numero_paginas = int(retorno.get("numero_paginas", 1))

        if pagina >= numero_paginas:
            break

        pagina += 1

    return todos_produtos
