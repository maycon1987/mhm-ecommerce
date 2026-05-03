from fastapi import Body

@router.post("/produtos")
def criar_produto(produto: dict = Body(...)):
    data = supabase.table("produtos").insert(produto).execute()
    return data.data
