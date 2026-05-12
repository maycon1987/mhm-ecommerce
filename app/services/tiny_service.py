import os
import requests
import time


def get_tiny_token():
    token = os.getenv("TINY_TOKEN")
    if not token:
        raise Exception("TINY_TOKEN não configurado")
    return token


def _obter_com_retry(tiny_id: str, tentativas: int = 3, delay: float = 2.0):
    """Tenta obter produto com retry em caso de erro de rede."""
    ultimo_erro = None
    for i in range(tentativas):
        try:
            return obter_produto_tiny(tiny_id)
        except Exception as e:
            ultimo_erro = e
            if i < tentativas - 1:
                time.sleep(delay * (i + 1))  # delay crescente: 2s, 4s, 6s
    raise ultimo_erro


def buscar_produtos_tiny(pagina: int = None):
    """
    Busca produtos do Tiny.
    Para produtos com grade (tipoVariacao=P), busca o detalhe e expande as variações.
    """
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"

    todos_produtos = []
    pagina_inicio = pagina if pagina else 1
    pagina_fim = pagina if pagina else None

    p = pagina_inicio
    while True:
        params = {"token": token, "formato": "JSON", "pagina": p}
        response = requests.get(url, params=params, timeout=30)

        if response.status_code != 200:
            break

        data = response.json()
        retorno = data.get("retorno", {})

        if retorno.get("status") != "OK":
            break

        produtos = retorno.get("produtos", [])
        if not produtos:
            break

        for item in produtos:
            if not isinstance(item, dict):
                continue
            prod = item.get("produto", {})
            if not isinstance(prod, dict):
                continue

            tiny_id = str(prod.get("id") or "")
            nome = (prod.get("nome") or "").strip()
            categoria = (prod.get("categoria") or "").strip()
            imagem_url = _extrair_imagem(prod)
            tipo_variacao = (prod.get("tipoVariacao") or "").strip()

            # Produto com grade — busca detalhe completo
            if tipo_variacao == "P" or not categoria:
                try:
                    time.sleep(0.5)  # delay maior para evitar Resource unavailable
                    detalhe = _obter_com_retry(tiny_id)
                    categoria = (detalhe.get("categoria") or categoria).strip()
                    if not imagem_url:
                        imagem_url = detalhe.get("imagem_url")

                    # Processa variações da grade
                    variacoes = detalhe.get("variacoes") or []
                    if variacoes and categoria:
                        for var_item in variacoes:
                            if isinstance(var_item, dict) and "grade" in var_item:
                                var = var_item
                            else:
                                var = var_item.get("variacao", var_item) if isinstance(var_item, dict) else {}

                            grade = var.get("grade", {})
                            quantidade = list(grade.values())[0] if grade else "1un"

                            todos_produtos.append({
                                "tiny_id":     str(var.get("id") or tiny_id),
                                "nome":        f"{nome} - {quantidade}",
                                "sku":         var.get("codigo") or prod.get("codigo"),
                                "preco":       var.get("preco") or prod.get("preco"),
                                "preco_varejo": var.get("preco") or prod.get("preco"),
                                "estoque":     prod.get("estoqueAtual") or 0,
                                "imagem_url":  imagem_url,
                                "categoria":   categoria,
                                "peso":        detalhe.get("peso") or 0,
                                "largura":     detalhe.get("largura") or 0,
                                "altura":      detalhe.get("altura") or 0,
                                "comprimento": detalhe.get("comprimento") or 0,
                            })
                        continue  # Já processou as variações, pula o produto pai

                    # Sem variações de grade, trata como produto simples
                    todos_produtos.append({
                        "tiny_id":     tiny_id,
                        "nome":        nome,
                        "sku":         prod.get("codigo"),
                        "preco":       detalhe.get("preco") or prod.get("preco"),
                        "preco_varejo": detalhe.get("preco") or prod.get("preco"),
                        "estoque":     prod.get("estoqueAtual") or 0,
                        "imagem_url":  imagem_url,
                        "categoria":   categoria,
                        "peso":        detalhe.get("peso") or 0,
                        "largura":     detalhe.get("largura") or 0,
                        "altura":      detalhe.get("altura") or 0,
                        "comprimento": detalhe.get("comprimento") or 0,
                    })
                    continue

                except Exception as e:
                    nome_erro = nome or tiny_id
                    raise Exception(f"{nome_erro}: {e}")

            # Produto simples sem grade
            todos_produtos.append({
                "tiny_id":     tiny_id,
                "nome":        nome,
                "sku":         prod.get("codigo"),
                "preco":       prod.get("preco"),
                "preco_varejo": prod.get("preco"),
                "estoque":     prod.get("estoqueAtual") or 0,
                "imagem_url":  imagem_url,
                "categoria":   categoria,
                "peso":        prod.get("peso_bruto") or prod.get("peso") or 0,
                "largura":     prod.get("largura") or 0,
                "altura":      prod.get("altura") or 0,
                "comprimento": prod.get("comprimento") or 0,
            })

        numero_paginas = int(retorno.get("numero_paginas", 1))

        if pagina_fim and p >= pagina_fim:
            break
        if p >= numero_paginas:
            break

        p += 1

    return todos_produtos


def buscar_numero_paginas_tiny():
    """Retorna o número total de páginas do Tiny."""
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produtos.pesquisa.php"
    params = {"token": token, "formato": "JSON", "pagina": 1}
    response = requests.get(url, params=params, timeout=30)
    data = response.json()
    retorno = data.get("retorno", {})
    return int(retorno.get("numero_paginas", 1))


def _extrair_imagem(produto: dict):
    anexos = produto.get("anexos") or []

    if isinstance(anexos, list) and len(anexos) > 0:
        primeiro = anexos[0]
        if isinstance(primeiro, dict):
            anexo = primeiro.get("anexo")
            if isinstance(anexo, str):
                return anexo
            elif isinstance(anexo, dict):
                return anexo.get("url")

    elif isinstance(anexos, dict):
        anexo = anexos.get("anexo")
        if isinstance(anexo, str):
            return anexo
        elif isinstance(anexo, list) and len(anexo) > 0:
            primeiro = anexo[0]
            if isinstance(primeiro, str):
                return primeiro
            elif isinstance(primeiro, dict):
                return primeiro.get("url")
        elif isinstance(anexo, dict):
            return anexo.get("url")

    return produto.get("imagem") or produto.get("urlImagem")


def obter_produto_tiny(tiny_id: str):
    token = get_tiny_token()
    url = "https://api.tiny.com.br/api2/produto.obter.php"
    params = {"token": token, "id": tiny_id, "formato": "JSON"}
    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Erro Tiny obter produto {tiny_id}: {response.text}")

    data = response.json()
    retorno = data.get("retorno", {})

    if retorno.get("status") != "OK":
        raise Exception(f"Erro Tiny produto {tiny_id}: {retorno}")

    produto = retorno.get("produto", {})
    imagem_url = _extrair_imagem(produto)

    # Extrai variações da grade
    variacoes_raw = produto.get("variacoes") or []
    variacoes = []
    for v in variacoes_raw:
        if isinstance(v, dict):
            var = v.get("variacao", v)
            if var:
                variacoes.append(var)

    return {
        "tiny_id":     tiny_id,
        "nome":        produto.get("nome"),
        "sku":         produto.get("codigo"),
        "preco":       produto.get("preco"),
        "preco_varejo": produto.get("preco"),
        "estoque":     produto.get("estoqueAtual") or 0,
        "peso":        produto.get("peso_bruto") or produto.get("peso_liquido") or produto.get("peso") or 0,
        "comprimento": produto.get("comprimento") or 0,
        "largura":     produto.get("largura") or 0,
        "altura":      produto.get("altura") or 0,
        "categoria":   produto.get("categoria"),
        "ncm":         produto.get("ncm"),
        "descricao":   produto.get("descricao_complementar"),
        "imagem_url":  imagem_url,
        "variacoes":   variacoes,
        "tipo_variacao": produto.get("tipoVariacao"),
    }
