ERT v2.0

O ERT é uma aplicação com interface gráfica (PySide6) focada no processamento, inversão e visualização de dados de eletrorresistividade. 
O software suporta Caminhamento Elétrico (ERT) e Sondagem Elétrica Vertical (SEV), integrando restrições geológicas para otimizar os resultados.
Funcionalidades

    Processamento ERT (2D): Inversão de arranjos dipolo-dipolo utilizando a biblioteca PyGIMLi, com geração automática de pseudo-seções e modelos interpretativos.

    Processamento SEV (1D): Inversão para arranjo Schlumberger com busca automática do número ótimo de camadas (critério AIC) e correção de saltos de embreagem (MN/2).

    Integração Geológica: Permite inserir dados litológicos e estruturais prévios (baseado em Palacky, 1987) para definir pesos, normas (L1/L2) e limites lógicos na inversão.

    Exportação 3D: Geração de arquivos consolidados (CSV e VTK para visualização no ParaView) e mapas de níveis, a partir de duas ou mais linhas com coordenadas configuradas (essa parte ainda está em melhoria)

Requisitos e Instalação

O programa foi desenvolvido em Python e requer bibliotecas matemáticas, de interface e de modelagem geofísica. Recomenda-se o uso de um ambiente virtual (venv ou conda).
Passo a passo (Windows e Linux)

1. Clone o repositório ou baixe os arquivos

2. Crie e ative um ambiente virtual (Opcional, mas recomendado)

3. Instale as dependências
O núcleo de inversão 2D exige o pygimli. Instale as dependências padrão através do pip:

Bash

pip install numpy pandas matplotlib scipy PySide6 odfpy pygimli

(A biblioteca odfpy é necessária para leitura nativa de planilhas .ods).

Estrutura e Importação de Arquivos

A interface gráfica possui a aba "1 · Dados" onde os arquivos devem ser importados. O programa aceita múltiplos arquivos simultaneamente.
Caminhamento Elétrico (ERT)

    Formato suportado: .txt ou .dat (Padrão RES2DINV).

    Estrutura: Cabeçalho padrão contendo nome, espaçamento, código do arranjo (3 para dipolo-dipolo), número de leituras e os dados estruturados em 4 colunas (x, a, n, rhoa).

    Correções automáticas: O sistema converte automaticamente vírgulas decimais para pontos.

Sondagem Elétrica Vertical (SEV)

    Formatos suportados: .ods, .xlsx, .xls ou .txt simples.

    Estrutura em Planilha: O arquivo pode conter múltiplas abas (uma SEV por aba). O programa lê a partir da primeira linha numérica buscando as colunas AB/2, MN/2, Fator Geométrico (K) e ρa.

    Estrutura em Texto (.txt): Arquivo sem cabeçalho obrigatório (linhas com # são ignoradas), contendo 3 colunas separadas por espaço: AB/2, MN/2 e ρa.

Configuração de Coordenadas (Modelagem 3D)

Para exportar os resultados em 3D ou gerar mapas de níveis:

    Importe os arquivos na interface.

    Clique com o botão direito sobre o arquivo na lista.

    Selecione "Definir coordenadas da linha…" e insira as coordenadas da origem (E, N) e o azimute.

Como Executar

Com o ambiente virtual ativado e as dependências instaladas, execute o arquivo principal no terminal:

    Windows:
    DOS

    python geofisica.py

    Linux:
    Bash

    python3 geofisica.py

O processamento é guiado pelas abas laterais da interface (Dados > Configuração > Geologia). Os resultados serão exportados automaticamente na pasta definida na aba de Dados.
