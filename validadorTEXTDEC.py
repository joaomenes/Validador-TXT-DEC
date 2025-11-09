import json
import sys
from datetime import datetime
from typing import List, Dict

sys.stdout.reconfigure(encoding='utf-8')

class ValidadorLayout:
    def __init__(self, schema_path: str):
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)
        self.registros = self.schema.get("registros", {})
        self.max_pos = self._calcular_max_pos()

    def _calcular_max_pos(self) -> int:
        maior = 0
        for reg in self.registros.values():
            for campo in reg.get("campos", []):
                fim = campo.get("posicao_fim", 0)
                maior = max(maior, fim)
        return maior

    def _pos_para_campo(self, campos: List[Dict]) -> Dict[int, Dict]:
        mapa = {}
        for campo in campos:
            ini = campo["posicao_inicio"]
            fim = campo["posicao_fim"]
            for p in range(ini, fim + 1):
                mapa[p] = campo
        return mapa

    def _validar_char_para_campo(self, ch: str, campo: Dict) -> bool:
        nome = campo.get("nome", "").lower()
        formato = campo.get("formato", "") or ""
        tipo = campo.get("tipo", "") or ""

        if ch == "":
            return True

        # fillers
        if "filler" in nome or "espaço" in nome or "espaços" in nome:
            return ch == " "

        if "dd/mm/aaaa" in formato or "data" in formato or "data" in nome:
            return ch.isdigit() or ch == "/"

        if "cpf" in nome or "cnpj" in nome:
            return ch.isdigit() or ch == " "

        if "numérico" in tipo.lower() or "numero" in nome or "nº" in nome:
            return ch.isdigit() or ch in {",", ".", " "}

        if "valor" in nome or "área" in nome or "participação" in nome or "area" in nome:
            return ch.isdigit() or ch in {",", ".", " "}

        if nome.strip() == "uf":
            return ch.isalpha()

        return ch >= " "

    def validar_arquivo(self, txt_path: str) -> List[str]:
        erros: List[str] = []
        erros_caractere: List[str] = []

        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            for num_linha, raw in enumerate(f, start=1):
                linha = raw.rstrip("\n\r")

                if not linha.strip():
                    continue

                tipo_registro = linha[0] if len(linha) > 0 else ""
                if tipo_registro not in self.registros:
                    erros.append(f"Linha {num_linha}: tipo de registro '{tipo_registro}' não reconhecido.")
                    continue

                registro_schema = self.registros[tipo_registro]
                campos = registro_schema.get("campos", [])
                mapa_pos = self._pos_para_campo(campos)

                # Validação de campos
                for campo in campos:
                    nome = campo["nome"]
                    ini, fim = campo["posicao_inicio"], campo["posicao_fim"]
                    tamanho = campo.get("tamanho", fim - ini + 1)
                    valor_fixo = campo.get("valor_fixo", "")
                    pode_ficar_vazio = campo.get("pode_ficar_vazio", False)
                    obrigatorio = campo.get("obrigatorio", False)
                    formato = (campo.get("formato") or "").lower()

                    trecho = linha[ini - 1:fim]
                    valor_preenchido = bool(trecho.strip())

                    if "od0a" in nome.lower() or "fim de registro" in nome.lower():
                        continue

                    # Campo obrigatório
                    if obrigatorio and not valor_preenchido:
                        erros.append(f"Linha {num_linha}: campo obrigatório '{nome}' vazio. Posições {ini}-{fim}.")
                        continue

                    # Campo opcional — só valida se houver valor
                    if pode_ficar_vazio and not valor_preenchido:
                        continue

                    # Tamanho
                    if len(trecho) != tamanho:
                        erros.append(f"Linha {num_linha}: campo '{nome}' com tamanho incorreto ({ini}-{fim}).")

                    
                    if valor_fixo.strip() and trecho.strip() != valor_fixo.strip():
                        erros.append(f"Linha {num_linha}: campo '{nome}' inválido. Esperado '{valor_fixo.strip()}', encontrado '{trecho.strip()}'. Posições {ini}-{fim}.")

                    
                    if "dd/mm/aaaa" in formato and valor_preenchido:
                        try:
                            datetime.strptime(trecho.strip(), "%d/%m/%Y")
                        except Exception:
                            erros.append(f"Linha {num_linha}: campo '{nome}' com data inválida '{trecho.strip()}'. Posições {ini}-{fim}.")

                # verificando posição
                limite = max(self.max_pos, len(linha))
                pos = 1
                blocos = []  # lista de blocos de erros com inicio e fim

                while pos <= limite:
                    ch = linha[pos - 1] if pos - 1 < len(linha) else ""
                    campo = mapa_pos.get(pos)
                    invalido = False

                    if not campo:
                        invalido = ch.strip() != ""
                    else:
                        nome_campo = campo.get("nome", "").lower()
                        if "od0a" not in nome_campo and "fim de registro" not in nome_campo:
                            if not self._validar_char_para_campo(ch, campo):
                                invalido = True

                    if invalido:
                        inicio = pos
                        fim = pos
                        conteudo = ch

                        while fim + 1 <= limite:
                            prox = linha[fim] if fim < len(linha) else ""
                            prox_campo = mapa_pos.get(fim + 1)
                            prox_invalido = False

                            if not prox_campo and prox.strip() != "":
                                prox_invalido = True
                            elif prox_campo and not self._validar_char_para_campo(prox, prox_campo):
                                prox_invalido = True

                            if prox_invalido:
                                fim += 1
                                conteudo += prox
                            else:
                                break
                        blocos.append((inicio, fim, conteudo))
                        pos = fim + 1
                    else:
                        pos += 1

                # informando caractere que pode gerar erro
                for inicio, fim, conteudo in blocos:
                    erros.append(
                        f"Linha {num_linha}: caracteres inválidos ou fora de posição esperada. "
                        f"Posições {inicio}-{fim}. Conteúdo encontrado: '{conteudo}'"
                    )

        # alerta sobre erro de possível caractere “�”
        if erros_caractere:
            erros.append("\nATENÇÃO: O arquivo contém caracteres inválidos (�). Isso indica erro de codificação — exemplo: 'S�o Paulo'. Oriente o usuário a reabrir e salvar o arquivo novamente com codificação UTF-8 sem BOM.")
            erros.extend(erros_caractere)

        return erros


if __name__ == "__main__":
    schema = "jsonvalidador.json" #indica o arquivo json contendo as regras
    txt = "arquivo.txt" #indica o arquivo txt ou dec que vai ser validado

    validador = ValidadorLayout(schema)
    resultado = validador.validar_arquivo(txt)

    if resultado:
        print("Erros encontrados:")
        for e in resultado:
            print("-", e)
    else:
        print("Nenhum erro encontrado.")
