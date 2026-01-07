import json
import re
import unicodedata
from app.extensions import get_openai_client

def _normalize_text(value):
    if value is None:
        return ""
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def _extract_labeled_fields(text):
    normalized = _normalize_text(text)
    results = {}

    label_map = {
        "REF SOUQ": "ref_souq",
        "REF": "ref_souq",
        "COLECAO": "collection",
        "FORNECEDOR": "supplier",
        "CORNER": "corner",
        "DESCRICAO": "description",
        "ESTILISTA": "stylists",
        "MATERIA-PRIMA E COMPOSICAO": "main_fabric",
        "MATERIA-PRIMA": "main_fabric",
        "TECIDO PRINCIPAL": "main_fabric",
        "TECIDO": "main_fabric",
        "TAM. PILOTO": "pilot_size",
        "TAM. DA PILOTO": "pilot_size",
    }
    labels = sorted(label_map.keys(), key=len, reverse=True)
    label_pattern = "|".join(re.escape(label) for label in labels)

    pattern = re.compile(rf"(?P<label>{label_pattern})\s*:?\s*", re.IGNORECASE)
    matches = list(pattern.finditer(normalized))
    if not matches:
        return results

    for idx, match in enumerate(matches):
        label = match.group("label").upper()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        value = normalized[start:end].strip()

        if not value:
            continue

        value = re.split(r"\s{2,}|\n", value)[0].strip()
        if not value:
            continue

        key = label_map.get(label)
        if key and key not in results:
            results[key] = value

    return results


def _extract_extra_fields(text):
    normalized = _normalize_text(text)
    results = {}

    label_map = {
        "STATUS INTEGRACAO": "Status Integracao",
        "ORIGEM": "Origem",
        "INCOTERM": "Incoterm",
        "NCM": "NCM",
        "REFERENCIA NS": "Referencia NS",
        "REFERENCIA": "Referencia",
        "REF ESTILO": "Ref Estilo",
        "MARCA": "Marca",
        "LINHA": "Linha",
        "GRUPO": "Grupo",
        "SUB GRUPO": "Subgrupo",
        "GRADE": "Grade",
        "SUB GRADE": "Subgrade",
        "ENTRADA": "Entrada",
        "CANAL": "Canal",
        "FAIXA PRECO PLANEJADA": "Faixa Preco Planejada",
        "MES PLANEJADO": "Mes Planejado",
        "MES ENTRADA NA LOJA": "Mes Entrada na Loja",
        "PLANEJADO/PIR. COLECAO": "Planejado Pir Colecao",
        "FOC/PA": "FOC/PA",
        "N DO LACRE": "N do Lacre",
        "N. DO LACRE": "N do Lacre",
        "MATERIAL PRINCIPAL": "Material Principal",
        "COMP (CM)": "Comprimento (cm)",
        "LARG (CM)": "Largura (cm)",
        "ALTURA (CM)": "Altura (cm)",
        "DIAMETRO (CM)": "Diametro (cm)",
        "PESO LIQUIDO UNITARIO": "Peso Liquido Unitario",
        "DESCRICAO TITULO PECA": "Descricao Titulo Peca",
        "DESCRICAO DO SITE": "Descricao do Site",
        "PRE CUSTO/SERVICOS": "Pre Custo/Servicos",
        "CORES DO MODELO": "Cores do Modelo",
    }
    labels = sorted(label_map.keys(), key=len, reverse=True)
    label_pattern = "|".join(re.escape(label) for label in labels)

    pattern = re.compile(rf"(?P<label>{label_pattern})\s*:?\s*", re.IGNORECASE)
    matches = list(pattern.finditer(normalized))
    if not matches:
        return results

    for idx, match in enumerate(matches):
        label = match.group("label").upper()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        value = normalized[start:end].strip()

        if not value:
            continue

        value = re.split(r"\s{2,}|\n", value)[0].strip()
        if not value:
            continue

        display_label = label_map.get(label)
        if display_label and display_label not in results:
            results[display_label] = value

    return results


def _trim_value_at_labels(value, labels):
    if not value:
        return value
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"\b({label_pattern})\b", value, re.IGNORECASE)
    if not match:
        return value.strip()
    trimmed = value[:match.start()].strip()
    return trimmed if trimmed else None



def analyze_images_with_gpt4_vision(images_base64):
    if not images_base64:
        print("No images provided for GPT-4 Vision analysis")
        return None

    openai_client = get_openai_client()
    if not openai_client:
        print("OpenAI client not initialized")
        return None

    try:
        print(f"Analyzing {len(images_base64)} images with GPT-4 Vision (structured JSON output)...")

        content = [{
            "type": "text",
            "text": """Você é um especialista técnico de vestuário. Analise ATÉ 3 imagens e descreva APENAS UMA peça: a mais PROEMINENTE da primeira imagem (maior área de pixels do corpo da peça). Ignore outras peças, pessoas, rostos e o fundo. Não descreva características pessoais.

⚠️ Precisão:
- Quando algo não pode ser visto com clareza, escreva exatamente "nao_visivel".
- Nunca invente medidas reais em cm sem referência explícita. Prefira relações visuais (ex.: "punho parece 2–3x a largura do pesponto").
- Use termos técnicos (PT-BR) e normalize enums (ex.: gola={careca,V,role,redonda,colarinho,polo,quadrada,canoa,ombro_a_ombro}).

Procedimento em 3 PASSOS (obrigatório):
1) MACRO: identifique tipo de peça e categoria (malha/tricô, tecido plano, jeans).
2) VARREDURA POR REGIÕES (ordem e "lupa"):
   - Decote/gola → placket/vistas → ombro/ombreira → cava → mangas → punhos → corpo/frente → bolsos frente → recortes/penses → barra → costas completas → gola/capuz costas → centro costas → recortes/penses costas → bolsos costas → barra costas → interior visível (forro/entretela/vivos).
   Para cada região, examine bordas, quinas, encontros, rebatidos, pespontos, travetes/bartacks, folgas e simetria E/D.
3) VARREDURA TRANSVERSAL (categorias de detalhe):
   - Fechamentos (tipo, posição exata, quantidade, direção de abotoamento).
   - Componentes pequenos: casas (forma, posição e distância da borda), botões (diâmetro relativo), ilhoses, rebites, colchetes, zíper (invisível/aparente, espiral/dente, cursor, puxador).
   - Costuras/acabamentos: tipo de ponto (reta, overlock 3/4 fios, cobertura), número de passadas (simples/duplo/tríplice), distância de rebatido da borda, largura de viés/debrum, largura de ribana/bainha, limpeza interna visível.
   - Modelagem/volume: franzidos, pregas, nervuras/canelados, godê, evasê, ombro caído, raglan.
   - Padronagens/texturas: direção do fio/canelado, disposição de tranças, rapport aparente.
   - Etiquetas/elementos externos: etiqueta de marca aparente, patches, bordados, termocolantes.
   - Assimetria e diferenças Frente vs Costas; Esquerda vs Direita (se houver).

⚠️ IMPORTANTE - Classificação de Grupo e Subgrupo:
- No campo "grupo", retorne EXATAMENTE um destes valores: TECIDO PLANO, MALHA, TRICOT, JEANS.
- No campo "subgrupo", retorne EXATAMENTE um destes valores: BLAZER, BLUSA, BRINCO, CALÇA, CAMISA, CAMISA/CAMISÃO, CAMISETA, CARDIGÃ, JAQUETA, KAFTAN, REGATA, SAIA, TÚNICA.
- Use LETRAS MAIÚSCULAS e NÃO crie novos valores fora dessas listas.

SAÍDA: responda SOMENTE um JSON válido com este esquema (preencha tudo que conseguir; use "nao_visivel" quando não der):

{
  "identificacao": {
    "tipo_peca": "",
    "categoria": "",
    "grupo": "",
    "subgrupo": "",
    "confianca": 0.0
  },
  "visoes": {
    "frente": "...",
    "costas": "...",
    "mangas": "..."
  },
  "gola_decote": {
    "tipo": "",
    "altura_visual": "",
    "abertura_largura_visual": "",
    "acabamento": "",
    "detalhes": "",
    "confianca": 0.0
  },
  "mangas": {
    "comprimento": "",
    "modelo": "",
    "cava": "",
    "copa_modelagem": "",
    "punho": {
      "existe": true,
      "tipo": "",
      "largura_visual": "",
      "fechamento": ""
    },
    "pala_ou_recorte": "",
    "confianca": 0.0
  },
  "corpo": {
    "comprimento_visual": "",
    "caimento": "",
    "recortes": "...",
    "pences_pregas_franzidos": "...",
    "simetria_ED": "",
    "observacoes": ""
  },
  "fechamentos": {
    "tipo": "",
    "posicao": "",
    "quantidade_botoes": "nao_visivel",
    "botoes_espacamento_relativo": "",
    "direcao_abotoamento": "nao_visivel",
    "ziper": {
      "visibilidade": "nao_visivel",
      "tipo_dente": "nao_visivel",
      "comprimento_visual": ""
    }
  },
  "bolsos": {
    "existe": false,
    "lista": []
  },
  "barra_hem": {
    "formato": "",
    "acabamento": "",
    "largura_visual": "",
    "aberturas_fendas": ""
  },
  "textura_padronagem": {
    "tipo_trico_malha": "nao_visivel",
    "direcao": "nao_visivel",
    "rapport_ou_repeticao": "",
    "contraste_linha_pesponto": ""
  },
  "acabamentos_especiais": [],
  "diferencas_frente_costas": "...",
  "itens_nao_visiveis_ou_ambigos": [],
  "conclusao_checklist": {
    "varredura_regioes_ok": true,
    "varredura_transversal_ok": true,
    "campos_pendentes": []
  }
}

Retorne SOMENTE o JSON, sem texto adicional."""
        }]

        for img_b64 in images_base64[:3]:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high"
                }
            })

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=3000
        )

        json_response = response.choices[0].message.content

        try:
            analysis_data = json.loads(json_response)
            print(f"\n{'='*80}")
            print(f"ANÁLISE VISUAL GPT-4o (JSON ESTRUTURADO)")
            print(f"{'='*80}")
            print(f"Tipo de peça: {analysis_data.get('identificacao', {}).get('tipo_peca', 'N/A')}")
            print(f"Categoria: {analysis_data.get('identificacao', {}).get('categoria', 'N/A')}")
            print(f"Grupo: {analysis_data.get('identificacao', {}).get('grupo', 'N/A')}")
            print(f"Subgrupo: {analysis_data.get('identificacao', {}).get('subgrupo', 'N/A')}")
            print(f"Confiança: {analysis_data.get('identificacao', {}).get('confianca', 0.0)}")
            print(f"Gola/Decote: {analysis_data.get('gola_decote', {}).get('tipo', 'N/A')}")
            print(f"Mangas: {analysis_data.get('mangas', {}).get('comprimento', 'N/A')} - {analysis_data.get('mangas', {}).get('modelo', 'N/A')}")
            print(f"Fechamentos: {analysis_data.get('fechamentos', {}).get('tipo', 'N/A')}")
            print(f"{'='*80}\n")
            return analysis_data
        except json.JSONDecodeError as e:
            print(f"⚠️ Erro ao parsear JSON - usando fallback para texto bruto")
            print(f"Erro JSON: {e}")
            print(f"Retornando texto livre para compatibilidade...")
            return json_response

    except Exception as e:
        print(f"Error analyzing images with GPT-4 Vision: {e}")
        import traceback
        traceback.print_exc()
        return None


def has_technical_measurements(spec):
    measurement_fields = [
        'body_length', 'bust', 'hem_width', 'shoulder_to_shoulder',
        'neckline_depth', 'sleeve_length', 'waist', 'straight_armhole'
    ]

    for field in measurement_fields:
        value = getattr(spec, field, None)
        if value and str(value).strip():
            return True

    return False


def build_technical_drawing_prompt(spec, visual_analysis=None):
    garment_type = spec.description or "peça de vestuário"
    material_info = spec.composition or "malha/tecido padrão"

    material_details = ""
    if "tricô" in material_info.lower() or "malha" in material_info.lower():
        material_details = "Malha/tricô - representar textura com traço técnico"

    print(f"\n{'='*80}")
    print(f"GERANDO DESENHO TÉCNICO: Flat sketch limpo SEM COTAGEM")
    print(f"{'='*80}\n")

    constructive_details = []
    if spec.finishes:
        constructive_details.append(f"Acabamentos: {spec.finishes}")
    if spec.openings_details:
        constructive_details.append(f"Fechamentos: {spec.openings_details}")

    details_text = " | ".join(constructive_details) if constructive_details else "detalhes conforme análise visual"

    visual_section = ""
    if visual_analysis:
        if isinstance(visual_analysis, dict):
            ident = visual_analysis.get('identificacao', {})
            gola = visual_analysis.get('gola_decote', {})
            mangas = visual_analysis.get('mangas', {})
            corpo = visual_analysis.get('corpo', {})
            fechamentos = visual_analysis.get('fechamentos', {})
            bolsos = visual_analysis.get('bolsos', {})
            barra = visual_analysis.get('barra_hem', {})
            textura = visual_analysis.get('textura_padronagem', {})

            visual_parts = []

            if ident.get('tipo_peca'):
                visual_parts.append(f"TIPO: {ident['tipo_peca']} ({ident.get('categoria', 'N/A')})")

            if gola.get('tipo') and gola['tipo'] != 'nao_visivel':
                gola_desc = f"GOLA/DECOTE: {gola['tipo']}"
                if gola.get('altura_visual') and gola['altura_visual'] != 'nao_visivel':
                    gola_desc += f" - altura {gola['altura_visual']}"
                if gola.get('acabamento'):
                    gola_desc += f" - acabamento: {gola['acabamento']}"
                if gola.get('detalhes'):
                    gola_desc += f" - {gola['detalhes']}"
                visual_parts.append(gola_desc)

            if mangas.get('comprimento') and mangas['comprimento'] != 'nao_visivel':
                manga_desc = f"MANGAS: {mangas['comprimento']}"
                if mangas.get('modelo') and mangas['modelo'] != 'nao_visivel':
                    manga_desc += f" - modelo {mangas['modelo']}"
                if mangas.get('cava'):
                    manga_desc += f" - cava {mangas['cava']}"

                punho = mangas.get('punho', {})
                if punho.get('existe') and punho.get('tipo'):
                    manga_desc += f" - punho {punho['tipo']}"
                    if punho.get('largura_visual'):
                        manga_desc += f" ({punho['largura_visual']})"

                visual_parts.append(manga_desc)

            if corpo.get('comprimento_visual'):
                corpo_desc = f"CORPO: comprimento {corpo['comprimento_visual']}"
                if corpo.get('caimento'):
                    corpo_desc += f" - caimento {corpo['caimento']}"
                if corpo.get('recortes'):
                    corpo_desc += f" - recortes: {corpo['recortes']}"
                visual_parts.append(corpo_desc)

            if fechamentos.get('tipo') and fechamentos['tipo'] != 'nao_visivel':
                fech_desc = f"FECHAMENTOS: {fechamentos['tipo']}"
                if fechamentos.get('posicao'):
                    fech_desc += f" na {fechamentos['posicao']}"
                if fechamentos.get('quantidade_botoes') and fechamentos['quantidade_botoes'] != 'nao_visivel':
                    fech_desc += f" - {fechamentos['quantidade_botoes']} botões"
                if fechamentos.get('botoes_espacamento_relativo'):
                    fech_desc += f" ({fechamentos['botoes_espacamento_relativo']})"

                ziper = fechamentos.get('ziper', {})
                if ziper.get('visibilidade') and ziper['visibilidade'] != 'nao_visivel':
                    fech_desc += f" - zíper {ziper['visibilidade']}"

                visual_parts.append(fech_desc)

            if bolsos.get('existe') and bolsos.get('lista'):
                for bolso in bolsos['lista']:
                    if isinstance(bolso, dict):
                        bolso_desc = f"BOLSO: {bolso.get('tipo', 'N/A')}"
                        if bolso.get('posicao'):
                            bolso_desc += f" - {bolso['posicao']}"
                        if bolso.get('dimensao_visual'):
                            bolso_desc += f" ({bolso['dimensao_visual']})"
                        visual_parts.append(bolso_desc)
                    elif isinstance(bolso, str):
                        visual_parts.append(f"BOLSO: {bolso}")

            if barra.get('formato'):
                barra_desc = f"BARRA: {barra['formato']}"
                if barra.get('acabamento'):
                    barra_desc += f" - acabamento {barra['acabamento']}"
                if barra.get('largura_visual'):
                    barra_desc += f" ({barra['largura_visual']})"
                visual_parts.append(barra_desc)

            if textura.get('tipo_trico_malha') and textura['tipo_trico_malha'] != 'nao_visivel':
                tex_desc = f"TEXTURA: {textura['tipo_trico_malha']}"
                if textura.get('direcao') and textura['direcao'] != 'nao_visivel':
                    tex_desc += f" - direção {textura['direcao']}"
                visual_parts.append(tex_desc)

            acabamentos = visual_analysis.get('acabamentos_especiais', [])
            if acabamentos:
                visual_parts.append(f"ACABAMENTOS ESPECIAIS: {', '.join(acabamentos)}")

            diferencas = visual_analysis.get('diferencas_frente_costas', '')
            if diferencas and diferencas.strip():
                visual_parts.append(f"DIFERENÇAS FRENTE/COSTAS: {diferencas}")

            visual_description = "\n".join(visual_parts)

        else:
            visual_description = str(visual_analysis)

        visual_section = f"""
**REFERÊNCIA VISUAL DA PEÇA (BASE OBRIGATÓRIA - SEGUIR FIELMENTE):**
{visual_description}
"""

    prompt = f"""TAREFA:
Gere desenho técnico plano (flat sketch) vetorial LIMPO da peça de vestuário.
Este é um flat sketch profissional SEM DIMENSÕES (sem cotas, sem POMs).

TIPO DA PEÇA: {garment_type}

ENTRADAS:
- Material/composição: {material_info}
{material_details}
- Detalhes construtivos: {details_text}
{visual_section}

VISTAS OBRIGATÓRIAS:
- Frente e Costas (mesma escala), alinhadas VERTICALMENTE
- Manga em posição natural (quando aplicável)
- Detalhes ampliados (escala 1:2) de: gola/colarinho, punho, bolso, zíper, barra, cós, casas de botão (se aplicável)

ESTILO VISUAL:
- Fundo 100% branco (#FFFFFF); SEM corpo/manequim/cabide
- Traço preto; espessuras: 
  * Contorno: 0,75pt contínuo
  * Costuras/canelado: 0,35pt contínuo
  * Pesponto/linha de malha: 0,35pt tracejado
- Cinza 15-30% APENAS para sobreposição/forro/volume
- Simetria central indicada por linha ponto-traço (eixo central)
- Símbolos gráficos: botão (círculo 2-4mm), ilhós (anel), rebite (ponto sólido)

CORES E PADRÕES (REPRESENTAÇÃO TÉCNICA):
- Cores disponíveis: {spec.colors if spec.colors else 'não especificadas'}
- ATENÇÃO: Se a peça tiver padrão (LISTRADO, XADREZ, POÁ, ESTAMPADO, etc), REPRESENTAR graficamente usando TRAÇOS TÉCNICOS:
  * LISTRADO: desenhar linhas horizontais ou verticais paralelas (espaçamento uniforme) cobrindo TODA a área da peça
  * XADREZ: grid de linhas perpendiculares formando quadrados
  * POÁ: círculos pequenos distribuídos uniformemente
  * ESTAMPADO: indicar com padrão simplificado de formas geométricas ou orgânicas
- NÃO usar texturas fotorrealistas; apenas linhas técnicas limpas

DETALHES CONSTRUTIVOS (incluir todos aplicáveis):
- Textura/padronagem: representar com traço técnico (nervuras verticais, canelados, tranças com cruzamento claro)
- Golas/colarinho: tipo exato, altura proporcional, acabamento
- Punhos: tipo (ribana/dobrado/abotoado)
- Barras: acabamento (bainha/ribana/overlock)
- Recortes, pences, pregas, franzidos, dobras funcionais
- Fechamentos: tipo (zíper, botões, colchetes), posição e quantidade
- Casas de botão: posição centrada, quantidade
- Bolsos: tipo exato (faca, chapa, embutido, patch), tampas, vivos

NORMALIZAÇÃO:
- Corrigir perspectiva/distorções: alinhar eixo central
- Garantir simetria quando aplicável
- Remover sombras/elementos que não pertencem à construção
- Proporções visualmente balanceadas

CRITÉRIOS DE ACEITAÇÃO:
- Frente/Costas na mesma escala, perfeitamente centradas
- Eixo central indicado; simetria consistente
- Visual limpo, técnico e profissional
- SEM DIMENSÕES, SEM COTAS, SEM POMs (desenho limpo apenas)

NÃO FAZER:
- NÃO adicionar medidas ou dimensões (não solicitadas)
- NÃO incluir modelo/sombra realista/gradiente
- NÃO usar texturas fotorrealistas
- NÃO inventar detalhes não mencionados na referência visual"""

    return prompt


def process_specification_with_openai(text_content):
    openai_client = get_openai_client()
    if not openai_client:
        print("OpenAI client not initialized")
        return None

    try:
        labeled_fallback = _extract_labeled_fields(text_content)
        extra_fields = _extract_extra_fields(text_content)
        prompt = f"""Você é um especialista em análise de fichas técnicas de vestuário da marca SOUQ. Extraia TODAS as informações disponíveis do texto abaixo e retorne em formato JSON estruturado.

ESTRUTURA TÍPICA DA FICHA TÉCNICA SOUQ:
- Cabeçalho contém: REF SOUQ, COLEÇÃO, FORNECEDOR, CORNER, DESCRIÇÃO, ESTILISTA
- Corpo contém: OBSERVAÇÕES/AVIAMENTOS, MATÉRIA-PRIMA E COMPOSIÇÃO, CORES
- Abaixo: DESENHO TÉCNICO e fotos

REGRAS CRÍTICAS DE EXTRAÇÃO (PRIORIDADE MÁXIMA):

1. **FORNECEDOR** (supplier):
   - Rótulos possíveis: "FORNECEDOR:", "FORN:", "FABRICANTE:", "FOR:"
   - É o nome da EMPRESA que fabrica (ex: "FOR ADY", "RENASC", "TÊXTIL ABC", "MENEGOTTI")
   - NÃO confundir com matéria-prima ou tecido!

2. **CORNER** (corner):
   - Rótulos possíveis: "CORNER:", "DEPT:", "DEPARTAMENTO:", "MARCA:", "LINHA:"
   - É o departamento/seção/marca (ex: "SOUQ", "CASUAL", "PREMIUM", "FEMININO", "MASCULINO")
   - Geralmente está próximo ao cabeçalho junto com REF SOUQ

3. **MATÉRIA-PRIMA / TECIDO PRINCIPAL** (main_fabric):
   - Rótulos possíveis: "MATÉRIA-PRIMA:", "MATÉRIA-PRIMA E COMPOSIÇÃO:", "TECIDO:", "TECIDO PRINCIPAL:", "MATERIAL:", "MP:"
   - Extraia APENAS o nome do TECIDO/MATERIAL base
   - IGNORAR informações de estoque/logística entre parênteses
   - Exemplos:
     * "LUMINOUS - MENEGOTTI (ESTOQUE FOR ADY)" → extrair "LUMINOUS - MENEGOTTI"
     * "CREPE DE SEDA (LOTE 123)" → extrair "CREPE DE SEDA"
     * "MALHA CANELADA" → extrair "MALHA CANELADA"
     * "VISCOSE PESADA" → extrair "VISCOSE PESADA"
   - NÃO é o fornecedor!

4. **ESTILISTA** (stylists):
   - Rótulos possíveis: "ESTILISTA:", "DESIGNER:", "RESPONSÁVEL:"
   - Nome do(a) estilista responsável

5. **COMPOSIÇÃO QUÍMICA** (composition):
   - Rótulos possíveis: "COMPOSIÇÃO:", "COMP.:", "%"
   - Se houver porcentagem de materiais (ex: "100% algodão", "60% poliéster 40% viscose")
   - Se não houver, use null

IMPORTANTE:
- Extraia EXATAMENTE o que está em cada campo rotulado
- Para medidas, extraia o VALOR NUMÉRICO (ex: "64 cm" → "64 cm")
- Para datas, use formato YYYY-MM-DD quando possível
- Se uma informação NÃO estiver disponível, use null (não invente dados)
- Procure variações de rótulos se o padrão não for encontrado

CAMPOS OBRIGATÓRIOS A EXTRAIR:

1. **Identificação da Peça:**
   - ref_souq: Código/referência (campo "REF SOUQ:" ou "REF:")
   - description: Nome/descrição da peça (campo "DESCRIÇÃO:" ou "DESC:")
   - collection: Coleção (campo "COLEÇÃO:" ou "COL:")
   - supplier: Nome da EMPRESA fornecedora - NÃO é tecido/matéria-prima!
   - corner: Corner/departamento/marca - procure rótulos como CORNER, DEPT, LINHA
   - main_fabric: Matéria-prima/tecido principal - procure rótulos como MATÉRIA-PRIMA, TECIDO, MP
   - main_group: Grupo - DEVE SER: TECIDO PLANO, MALHA, TRICOT ou JEANS (MAIÚSCULAS)
   - sub_group: Subgrupo - DEVE SER: BLAZER, BLUSA, BRINCO, CALÇA, CAMISA, CAMISA/CAMISÃO, CAMISETA, CARDIGÃ, JAQUETA, KAFTAN, REGATA, SAIA ou TÚNICA (MAIÚSCULAS)

2. **Informações Comerciais:**
   - target_price: Preço alvo (campo "Target Price:")
   - store_month: Mês de loja (campo "MÊS LOJA:")
   - delivery_cd_month: Mês de entrega CD (campo "MÊS ENTREGA CD:")

3. **Prazos e Entregas:**
   - tech_sheet_delivery_date: Data entrega ficha técnica
   - pilot_delivery_date: Data entrega piloto
   - showcase_for: Mostruário para

4. **Equipe Envolvida:**
   - stylists: Estilista(s) responsável(is) (campo "ESTILISTA:")

5. **Materiais e Detalhes:**
   - composition: Composição química do tecido (ex: "100% algodão")
   - pattern: Estampa/padrão (Listrado, Floral, Xadrez, Liso, Poá)
   - colors: Cores disponíveis (campo "CORES:")
   - tags_kit: Observações e aviamentos (campo "OBSERVAÇÕES/AVIAMENTOS:")

6. **Especificações Técnicas:**
   - pilot_size: Tamanho piloto (campo "TAM. DA PILOTO:")
   - body_length: Comprimento corpo (cm)
   - sleeve_length: Comprimento manga (cm)
   - hem_width: Largura barra (cm)
   - shoulder_to_shoulder: Ombro a ombro (cm)
   - bust: Busto (cm)
   - waist: Cintura (cm)
   - straight_armhole: Cava reta (cm)
   - neckline_depth: Profundidade decote (cm)
   - openings_details: Aberturas e fechamentos
   - finishes: Acabamentos

7. **Design e Estilo:**
   - technical_drawing: Referência desenho técnico
   - reference_photos: Referências de fotos
   - specific_details: Detalhes específicos

**TEXTO DA FICHA TÉCNICA:**
{text_content}

Retorne um objeto JSON com TODOS os campos acima, usando null para informações não disponíveis."""

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": "Você é um especialista em análise de fichas técnicas de vestuário. Extraia TODAS as informações estruturadas encontradas no texto e retorne SOMENTE em formato JSON válido, sem texto adicional. Seja preciso na extração de medidas e valores numéricos."
            }, {
                "role": "user",
                "content": prompt
            }],
            response_format={"type": "json_object"},
            max_tokens=2500
        )

        content = response.choices[0].message.content
        if content:
            try:
                parsed_json = json.loads(content)

                flattened = {}
                for key, value in parsed_json.items():
                    if isinstance(value, dict):
                        flattened.update(value)
                    else:
                        flattened[key] = value

                print(f"\n{'='*80}")
                print(f"DADOS EXTRAÍDOS PELO OPENAI")
                print(f"{'='*80}")
                print(f"Total de campos: {len(flattened)}")

                campos_importantes = [
                    'ref_souq', 'description', 'collection', 'supplier',
                    'corner', 'main_fabric', 'stylists', 'composition',
                    'main_group', 'sub_group', 'pilot_size', 'body_length',
                    'bust', 'sleeve_length'
                ]

                print("\n📋 CAMPOS PRINCIPAIS:")
                for key in campos_importantes:
                    value = flattened.get(key)
                    if value is not None and value != "":
                        print(f"  ✓ {key}: {str(value)}")
                    else:
                        print(f"  ✗ {key}: (vazio/não encontrado)")

                print("\n📏 OUTROS CAMPOS:")
                for key, value in flattened.items():
                    if key not in campos_importantes and value is not None and value != "":
                        print(f"  - {key}: {str(value)[:80]}...")

                print(f"{'='*80}\n")
                if labeled_fallback:
                    supplier_fallback = labeled_fallback.get('supplier')
                    corner_fallback = labeled_fallback.get('corner')

                    if supplier_fallback:
                        flattened['supplier'] = supplier_fallback
                    if corner_fallback:
                        flattened['corner'] = corner_fallback
                if extra_fields:
                    flattened['extra_fields'] = extra_fields

                corner_value = flattened.get('corner')
                corner_value = _trim_value_at_labels(
                    corner_value,
                    [
                        "MES PLANEJADO",
                        "ENTRADA",
                        "MARCA",
                        "LINHA",
                        "COLECAO",
                        "REFERENCIA",
                        "REF ESTILO",
                        "GRUPO",
                        "SUB GRUPO",
                        "GRADE",
                        "SUB GRADE",
                    ],
                )
                if corner_value is None:
                    flattened['corner'] = None
                else:
                    flattened['corner'] = corner_value
                return flattened
            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {je}")
                return None
        else:
            return None
    except Exception as e:
        print(f"Error processing with OpenAI: {e}")
        import traceback
        traceback.print_exc()
        return None
