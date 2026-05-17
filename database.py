import os
import sqlite3
import unicodedata

from utils.default_vagas import DEFAULT_VAGAS

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rpg_bleach.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # Otimizações de performance para SQLite
    conn.execute("PRAGMA journal_mode=WAL;")  # Permite leitura e escrita simultâneas
    conn.execute("PRAGMA synchronous=NORMAL;") # Acelera escritas sem sacrificar muita segurança
    conn.execute("PRAGMA cache_size=-64000;") # Cache de 64MB para reduzir I/O de disco
    conn.execute("PRAGMA temp_store=MEMORY;") # Armazena tabelas temporárias na RAM
    return conn


DEFAULT_PERICIAS = [
    (
        'Zanjutsu',
        'Shinigami, Vaizard',
        'Arte de combate com Zanpakutō, unindo técnica, postura e conexão com a lâmina. +2% de força por nível.',
        0.02,
        'forca',
    ),
    (
        'Hakuda',
        'Shinigami, Vaizard',
        'Combate desarmado de curta distância, focado em golpes físicos, pressão e controle corporal. +2% de força por nível.',
        0.02,
        'forca',
    ),
    (
        'Hohō',
        'Shinigami, Vaizard',
        'Movimentação avançada dos Shinigamis, base do Shunpo e de técnicas evasivas. +2% de velocidade por nível.',
        0.02,
        'velocidade',
    ),
    (
        'Kidō',
        'Shinigami, Vaizard',
        'Domínio de Hadō, Bakudō e Kaidō, aumentando poder, estabilidade e acesso a feitiços. +2% de poder em Kidō por nível.',
        0.02,
        'kido',
    ),
    (
        'Kaidō',
        'Shinigami, Vaizard',
        'Kidō de cura e restauração espiritual, refinando tratamento de ferimentos e recuperação de energia. +2% em técnicas de Kaidō por nível.',
        0.02,
        'tecnica:Kaidō',
    ),
    (
        'Lucha',
        'Hollow, Arrancar, Vaizard',
        'Combate corpo a corpo de Hollows e Arrancars, guiado por instinto, pressão e adaptação física. +2% de força por nível.',
        0.02,
        'forca',
    ),
    (
        'Hierro',
        'Hollow, Arrancar, Vaizard',
        'Pele espiritual endurecida que funciona como armadura natural contra impactos e cortes. +2% de resistência por nível.',
        0.02,
        'resistencia',
    ),
    (
        'Regen',
        'Hollow, Arrancar, Vaizard',
        'Regeneração Hollow para recuperar danos e manter o corpo em combate. +2% em técnicas de regeneração por nível.',
        0.02,
        'tecnica:Regen',
    ),
    (
        'Cero',
        'Hollow, Arrancar, Vaizard',
        'Disparo concentrado de energia espiritual destrutiva. +2% de dano em técnicas de Cero por nível.',
        0.02,
        'tecnica:Cero',
    ),
    (
        'Sonido',
        'Hollow, Arrancar, Vaizard',
        'Movimentação de alta velocidade de Hollows e Arrancars para investidas e evasão. +2% de velocidade por nível.',
        0.02,
        'velocidade',
    ),
    (
        'Heilig Pfeil',
        'Quincy',
        'Controle de flechas espirituais Quincy para ataques precisos à distância. +2% em técnicas de Heilig Pfeil por nível.',
        0.02,
        'tecnica:Heilig Pfeil',
    ),
    (
        'Blut Vene',
        'Quincy',
        'Técnica defensiva Quincy que endurece o corpo com Reishi circulando nas veias. +2% de resistência por nível.',
        0.02,
        'resistencia',
    ),
    (
        'Blut Arterie',
        'Quincy',
        'Técnica ofensiva Quincy que canaliza Reishi pelas artérias para ampliar impacto e perfuração. +2% de força por nível.',
        0.02,
        'forca',
    ),
    (
        'Hirenkyaku',
        'Quincy',
        'Movimentação Quincy de alta velocidade usando plataformas de Reishi. +2% de velocidade por nível.',
        0.02,
        'velocidade',
    ),
    (
        'Vollständig',
        'Quincy',
        'Forma Quincy completa que eleva o corpo por meio de uma técnica de buff. Cada nível acima do inicial concede +1 turno em Quincy: Vollständig.',
        1.0,
        'turnos:Quincy: Vollständig',
    ),
    (
        'Soul Manipulation',
        'Fullbringer',
        'Manipulação da alma da matéria física para reduzir gasto e amplificar efeitos do Fullbring. +2% em técnicas de Soul por nível.',
        0.02,
        'tecnica:Soul',
    ),
    (
        'Object Affinity',
        'Fullbringer',
        'Sincronia com o objeto Fullbring para ampliar controle, impacto e eficiência de uso. +2% em força, velocidade e resistência por nível.',
        0.02,
        'forca,velocidade,resistencia',
    ),
    (
        'Bringer Light',
        'Fullbringer',
        'Movimentação Fullbringer ao puxar a alma do solo e do ar para acelerar deslocamentos. +2% de velocidade por nível.',
        0.02,
        'velocidade',
    ),
    (
        'Máscara',
        'Vaizard, Vizard, Visored',
        'Controle da máscara Hollow e da pressão híbrida. Cada nível acima do inicial concede +1 turno na técnica Máscara.',
        1.0,
        'turnos:Máscara',
    ),
]


PERICIA_ALIASES = {
    'heiligpfeil': ('heilingpfeil',),
    'objectaffinity': ('objectinfinity',),
    'regen': ('regeneracion', 'regeneracao', 'highspeedregeneration'),
    'soulmanipulation': ('soul',),
}


DEFAULT_TECNICAS = [
    # Zanjutsu
    ('Agitowari', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Corte descendente usado para partir a defesa do alvo.', 1),
    ('Beautiful Swordfight', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Sequência estilizada de golpes com Zanpakutō.', 1),
    ('Deadly Darts', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Arremesso ou controle ofensivo da lâmina em múltiplos ataques.', 1),
    ('Hitotsume: Nadegiri', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Corte único, amplo e preciso com grande alcance.', 1),
    ('Hōzan Kenbu', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Dança de lâminas com cortes sucessivos.', 1),
    ('Hōzuri', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Corte superficial e controlado feito com precisão.', 1),
    ('Ichigo Homerun', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Golpe de impacto que arremessa o alvo com a lâmina.', 1),
    ('Onibi', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Técnica de corte em investida para pressionar o inimigo.', 1),
    ('Ryōdan', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Corte de duas mãos usado para aumentar o poder do golpe.', 1),
    ('Senmaioroshi', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Série de cortes rápidos para dilacerar a defesa.', 1),
    ('Shitonegaeshi', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Técnica que prende ou desequilibra o oponente com a ponta da lâmina.', 1),
    ('Suikawari', 'Zanjutsu', 'Shinigami, Vaizard', 'Zanjutsu', 'Corte direto e pesado, normalmente aplicado de cima para baixo.', 1),

    # Hakuda
    ('Bukkomi Dogeza', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Investida corporal brusca usada como ataque de impacto.', 1),
    ('Chikangoroshi Savate', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Chute de combate corpo a corpo.', 1),
    ('Chikangoroshi Toekick', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Chute direto com a ponta do pé.', 1),
    ('Chōhigezutsuki', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Cabeçada ou golpe frontal de curta distância.', 1),
    ('Gatling Mad-Stomping', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Sequência rápida de pisões contra o alvo.', 1),
    ('Ikkotsu', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Golpe de punho único com força concentrada.', 1),
    ('Isshin Flying Double Knee', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Ataque aéreo usando ambos os joelhos.', 1),
    ('Isshin Handstand Dash', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Deslocamento ofensivo com apoio invertido.', 1),
    ('Kagamibiraki', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Golpe com as duas mãos para romper ou abrir a defesa.', 1),
    ('Kazaguruma', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Técnica giratória de arremesso ou impacto.', 1),
    ('Kūkaku Smash', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Golpe físico pesado de impacto direto.', 1),
    ('Kūkaku Heel Crush', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Ataque descendente com o calcanhar.', 1),
    ('Mashiro Drop Kick', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Chute voador aplicado em queda.', 1),
    ('Mashiro Kick', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Chute direto de alta velocidade.', 1),
    ('Mashiro Super Kick', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Chute reforçado com grande potência.', 1),
    ('Oni Dekopin', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Golpe concentrado com o dedo.', 1),
    ('Panty-Flash Tornado', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Ataque giratório usado para desorientar e atingir o alvo.', 1),
    ('Raiōken', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Rajada de socos extremamente velozes.', 1),
    ('Sandbag Beat', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Sequência de golpes corpo a corpo contra um alvo pressionado.', 1),
    ('Shunkō', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Combinação avançada de Hakuda e Kidō envolvendo o corpo em energia.', 1),
    ('Sōkotsu', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Ataque com dois punhos de impacto extremo.', 1),
    ('Super Harisen Slipper', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Golpe físico usado como ataque cômico de impacto.', 1),
    ('Taketonbo', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Técnica de arremesso que lança o oponente.', 1),
    ('Takigoi', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Manobra defensiva para resistir ou redirecionar impacto.', 1),
    ('Tesshō', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Golpe de palma com força concentrada.', 1),
    ('Tsukiyubi', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Empurrão de dedo capaz de lançar o alvo.', 1),
    ('Tsurigaki', 'Hakuda', 'Shinigami, Vaizard', 'Hakuda', 'Técnica de chute ou varredura para controlar distância.', 1),

    # Hohō
    ('Shunpo', 'Hohō', 'Shinigami, Vaizard', 'Hohō', 'Passo relâmpago usado para deslocamento rápido.', 1),
    ('Senka', 'Hohō', 'Shinigami, Vaizard', 'Hohō', 'Variação de Shunpo para se posicionar atrás do alvo.', 1),
    ('Speed Clones', 'Hohō', 'Shinigami, Vaizard', 'Hohō', 'Movimento rápido que cria imagens residuais.', 1),
    ('Utsusemi', 'Hohō', 'Shinigami, Vaizard', 'Hohō', 'Técnica de evasão que deixa uma imagem ou peça de roupa como substituto.', 1),

    # Hollow/Arrancar/Visored
    ('Cero', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Disparo de energia espiritual concentrada.', 1),
    ('Bala', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Projétil espiritual mais rápido e menor que um Cero.', 1),
    ('Cero Doble', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Cero que absorve e devolve o disparo inimigo junto ao próprio ataque.', 1),
    ('Cero Córnea', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Variação de Cero disparada pelo olho.', 1),
    ('Cero Sincrético', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Cero combinado por mais de um usuário.', 1),
    ('Gran Rey Cero', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Cero superior associado aos Espada.', 1),
    ('Cero Oscuras', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Cero negro usado por Espada em estado liberado.', 0),
    ('Cero Metralleta', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Rajada contínua de múltiplos Ceros.', 1),
    ('Mashiro Super Cero', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Variação de Cero usada por Mashiro.', 1),
    ('La Mirada', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Cero disparado a partir da visão.', 1),
    ('Cero Creciente', 'Cero', 'Hollow, Arrancar, Vaizard', 'Cero', 'Variação crescente de Cero.', 1),
    ('Sonído', 'Sonido', 'Hollow, Arrancar, Vaizard', 'Sonido', 'Movimento de alta velocidade usado por Arrancar.', 1),
    ('Gemelos Sonído', 'Sonido', 'Hollow, Arrancar, Vaizard', 'Sonido', 'Variação avançada que cria duplicatas por movimento.', 1),
    ('Hierro', 'Hierro', 'Hollow, Arrancar, Vaizard', 'Hierro', 'Endurecimento espiritual da pele para resistir a dano.', 1),
    ('High-Speed Regeneration', 'Regen', 'Hollow, Arrancar, Vaizard', 'Regen', 'Regeneração acelerada de ferimentos e membros perdidos.', 1),
    ('Máscara', 'Máscara', 'Vaizard, Vizard, Visored', 'Máscara', 'Uso da máscara Hollow para liberar poder híbrido por turnos.', 1),

    # Quincy
    ('Heilig Pfeil', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Flecha espiritual formada por Reishi.', 1),
    ('Klavier', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Rajada rápida de múltiplas flechas espirituais.', 1),
    ('Licht Regen', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Chuva de flechas espirituais disparadas em sequência.', 1),
    ('Qual Kreis', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Cerco de arcos espirituais que disparam contra o alvo.', 1),
    ('Hirenkyaku', 'Hirenkyaku', 'Quincy', 'Hirenkyaku', 'Movimento rápido ao cavalgar o fluxo de Reishi sob os pés.', 1),
    ('Blut Vene', 'Blut Vene', 'Quincy', 'Blut Vene', 'Forma defensiva do Blut para reduzir dano recebido.', 1),
    ('Blut Arterie', 'Blut Arterie', 'Quincy', 'Blut Arterie', 'Forma ofensiva do Blut para aumentar poder de ataque.', 1),
    ('Blut Vene Anhaben', 'Blut Vene', 'Quincy', 'Blut Vene', 'Campo defensivo avançado criado com Blut Vene.', 1),
    ('Quincy: Vollständig', 'Vollständig', 'Quincy', 'Vollständig', 'Forma Quincy completa que eleva as capacidades espirituais.', 1),
    ('Sklaverei', 'Vollständig', 'Quincy', 'Vollständig', 'Absorção avançada de Reishi usada em Vollständig.', 1),
    ('Ransōtengai', 'Vollständig', 'Quincy', 'Vollständig', 'Controle do próprio corpo por fios espirituais.', 1),
    ('Kirchenlied: Sankt Zwinger', 'Vollständig', 'Quincy', 'Vollständig', 'Feitiço Quincy de proteção/ofensa em área sagrada.', 1),
    ('Sprenger', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Armadilha Quincy de energia usando Seele Schneider.', 1),
    ('Heizen', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Técnica Gintō que corta o alvo com energia espiritual.', 1),
    ('Gritz', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Técnica Gintō de contenção espiritual.', 1),
    ('Wolke', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Técnica Gintō que cria uma almofada ou massa espiritual.', 1),
    ('Seele Schneider', 'Heilig Pfeil', 'Quincy', 'Heilig Pfeil', 'Lâmina/flecha Quincy que vibra para cortar Reishi.', 1),

    # Fullbringer
    ('Fullbring', 'Soul', 'Fullbringer', 'Soul', 'Manipulação da alma presente em matéria física.', 1),
    ('Soul Manipulation', 'Soul', 'Fullbringer', 'Soul', 'Uso direto da alma de objetos ou ambiente para gerar efeitos.', 1),
    ('Bringer Light', 'Bringer Light', 'Fullbringer', 'Bringer Light', 'Movimento acelerado ao puxar a alma do chão e do ar.', 1),
    ('Object Affinity', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Afinidade com um objeto que desperta uma habilidade única.', 1),
    ('Book of the End', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring baseado em uma espada/marcador capaz de inserir presença no passado.', 1),
    ('Cross of Scaffold', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring de Kūgo Ginjō ligado ao pingente em forma de cruz.', 1),
    ('Dollhouse', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring de Riruka ligado a objetos de afeição.', 1),
    ('Love Gun', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Variação ofensiva do Fullbring de Riruka.', 1),
    ('Invaders Must Die', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring de Yukio associado ao controle digital.', 1),
    ('Time Tells No Lies', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring de Giriko ligado a condições temporais.', 1),
    ('Dirty Boots', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring de Jackie que aumenta poder conforme as botas se sujam.', 1),
    ('Jackpot Knuckle', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Fullbring de Moe Shishigawara baseado em sorte.', 1),
    ('Brazo Derecha de Gigante', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Braço direito ofensivo/defensivo de Yasutora Sado.', 1),
    ('Brazo Izquierda del Diablo', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Braço esquerdo ofensivo de Yasutora Sado.', 1),
    ('El Directo', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Golpe direto reforçado pelo Fullbring de Sado.', 1),
    ('La Muerte', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Ataque de energia do braço esquerdo de Sado.', 1),
    ('Digital Radial Invaders', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Ataque digital radial associado ao Fullbring de Yukio.', 1),
    ('Addiction Shot', 'Object Affinity', 'Fullbringer', 'Object Affinity', 'Técnica de disparo associada a uma habilidade Fullbring.', 1),
]


BLOCKED_TECNICA_VARIANT_NAMES = (
    # Hohō avançado/derivado
    'Senka',
    'Speed Clones',
    'Utsusemi',

    # Hollow/Arrancar variantes
    'Cero Doble',
    'Cero Córnea',
    'Cero Sincrético',
    'Gran Rey Cero',
    'Cero Oscuras',
    'Cero Metralleta',
    'Mashiro Super Cero',
    'La Mirada',
    'Cero Creciente',
    'Gemelos Sonído',

    # Técnicas avançadas específicas
    'Shunkō',
    'Blut Vene Anhaben',
    'Klavier',
    'Licht Regen',
    'Qual Kreis',
    'Sklaverei',
    'Ransōtengai',
    'Kirchenlied: Sankt Zwinger',
    'Sprenger',
    'Heizen',
    'Gritz',
    'Wolke',
    'Seele Schneider',

    # Fullbrings únicos
    'Book of the End',
    'Cross of Scaffold',
    'Dollhouse',
    'Love Gun',
    'Invaders Must Die',
    'Time Tells No Lies',
    'Dirty Boots',
    'Jackpot Knuckle',
    'Brazo Derecha de Gigante',
    'Brazo Izquierda del Diablo',
    'El Directo',
    'La Muerte',
    'Digital Radial Invaders',
    'Addiction Shot',
)


def _pericia_key(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(char for char in ascii_text.casefold() if char.isalnum())


BLOCKED_TECNICA_VARIANTS = {_pericia_key(name) for name in BLOCKED_TECNICA_VARIANT_NAMES}


def _upsert_default_pericias(cursor):
    existing = {
        _pericia_key(nome): pericia_id
        for pericia_id, nome in cursor.execute('SELECT id, nome FROM pericias_base').fetchall()
    }
    for nome, raca, descricao, bonus_valor, atributo_afetado in DEFAULT_PERICIAS:
        key = _pericia_key(nome)
        pericia_id = existing.get(key)
        if not pericia_id:
            for alias in PERICIA_ALIASES.get(key, ()):
                pericia_id = existing.get(alias)
                if pericia_id:
                    break
        if pericia_id:
            cursor.execute(
                '''
                UPDATE pericias_base
                SET nome = ?, raca = ?, descricao = ?, bonus_valor = ?, atributo_afetado = ?
                WHERE id = ?
                ''',
                (nome, raca, descricao, bonus_valor, atributo_afetado, pericia_id),
            )
            continue

        cursor.execute(
            '''
            INSERT INTO pericias_base (nome, raca, descricao, bonus_valor, atributo_afetado)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (nome, raca, descricao, bonus_valor, atributo_afetado),
        )
        existing[key] = cursor.lastrowid


def _upsert_default_tecnicas(cursor):
    existing = {
        (_pericia_key(nome), _pericia_key(categoria)): tecnica_id
        for tecnica_id, nome, categoria in cursor.execute(
            """
            SELECT id, nome, categoria
            FROM tecnicas
            WHERE classificacao = 'oficial'
            """
        ).fetchall()
    }

    for nome, categoria, raca, requer_pericia, descricao, liberada in DEFAULT_TECNICAS:
        key = (_pericia_key(nome), _pericia_key(categoria))
        liberada = 0 if _pericia_key(nome) in BLOCKED_TECNICA_VARIANTS else liberada
        tecnica_id = existing.get(key)
        if tecnica_id:
            cursor.execute(
                """
                UPDATE tecnicas
                SET nome = ?, categoria = ?, classificacao = 'oficial',
                    descricao = ?, raca = ?, requer_pericia = ?, liberada = ?
                WHERE id = ?
                """,
                (nome, categoria, descricao, raca, requer_pericia, int(bool(liberada)), tecnica_id),
            )
            continue

        cursor.execute(
            """
            INSERT INTO tecnicas
                (nome, categoria, classificacao, descricao, raca, requer_pericia, liberada)
            VALUES (?, ?, 'oficial', ?, ?, ?, ?)
            """,
            (nome, categoria, descricao, raca, requer_pericia, int(bool(liberada))),
        )
        existing[key] = cursor.lastrowid


def _upsert_default_vagas(cursor):
    existing_rows = cursor.execute('SELECT nome, vaga_id FROM vagas').fetchall()
    existing_by_name = {_pericia_key(nome): nome for nome, vaga_id in existing_rows}
    existing_by_id = {vaga_id: nome for nome, vaga_id in existing_rows if vaga_id}

    for vaga in DEFAULT_VAGAS:
        if len(vaga) == 5:
            nome, categoria, limite, vaga_id, descricao = vaga
            restricao_raca = "Shinigami" if categoria == "Zanpakuto" else "Nenhuma"
        else:
            nome, categoria, limite, vaga_id, descricao, restricao_raca = vaga
        key = _pericia_key(nome)
        current_nome = existing_by_name.get(key) or existing_by_id.get(vaga_id)
        if current_nome:
            cursor.execute(
                '''
                UPDATE vagas
                SET nome = ?, categoria = ?, limite = ?, restricao_raca = ?, vaga_id = ?, descricao = ?
                WHERE nome = ?
                ''',
                (nome, categoria, limite, restricao_raca, vaga_id, descricao, current_nome),
            )
            if current_nome != nome:
                cursor.execute('UPDATE player_vagas SET vaga_nome = ? WHERE vaga_nome = ?', (nome, current_nome))
                cursor.execute('UPDATE vagas_vinculo SET vaga_pai = ? WHERE vaga_pai = ?', (nome, current_nome))
                cursor.execute('UPDATE vagas_vinculo SET vaga_filha = ? WHERE vaga_filha = ?', (nome, current_nome))
            existing_by_name[key] = nome
            existing_by_id[vaga_id] = nome
            continue

        cursor.execute(
            '''
            INSERT INTO vagas (nome, categoria, atributo, limite, restricao_raca, vaga_id, descricao)
            VALUES (?, ?, 'todos', ?, ?, ?, ?)
            ''',
            (nome, categoria, limite, restricao_raca, vaga_id, descricao),
        )
        existing_by_name[key] = nome
        existing_by_id[vaga_id] = nome

def setup_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS config_logs (id INTEGER PRIMARY KEY CHECK (id = 1), canal_logs INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS config_historico (id INTEGER PRIMARY KEY CHECK (id = 1), canal_historico INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS config_comandos (id INTEGER PRIMARY KEY CHECK (id = 1), canal_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS canais_bloqueados_bot (canal_id INTEGER PRIMARY KEY)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS config_pretensao (
            id INTEGER PRIMARY KEY CHECK (id = 1), canal_id INTEGER, hora_abrir TEXT DEFAULT '19:00',
            hora_fechar TEXT DEFAULT '22:00', dias_semana TEXT DEFAULT '0,1,2,3,4,5,6', anunciado INTEGER DEFAULT 0)''')
        cursor.execute("INSERT OR IGNORE INTO config_pretensao (id) VALUES (1)")
        cursor.execute('''CREATE TABLE IF NOT EXISTS personagens (
            user_id INTEGER PRIMARY KEY, nome TEXT, raca TEXT, forca INTEGER DEFAULT 0,
            velocidade INTEGER DEFAULT 0, resistencia INTEGER DEFAULT 0, pontos_livres INTEGER DEFAULT 0,
            limite_nivel INTEGER DEFAULT 0, slots_potencial INTEGER DEFAULT 1, 
            pontos_pericia INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS potenciais (
            nome TEXT PRIMARY KEY, multiplicador REAL, duracao INTEGER, cooldown INTEGER DEFAULT 0,
            custo_ativacao INTEGER DEFAULT 0, custo_turno INTEGER DEFAULT 0,
            mult_forca REAL DEFAULT 0, mult_velocidade REAL DEFAULT 0,
            mult_resistencia REAL DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS player_potencial (
            user_id INTEGER, potencial TEXT, extra REAL DEFAULT 0, ativo INTEGER DEFAULT 0,
            turnos INTEGER DEFAULT 0, cooldown INTEGER DEFAULT 0, dur_mod INTEGER DEFAULT 0,
            cd_mod INTEGER DEFAULT 0, mult_override REAL DEFAULT 0, imagem_url TEXT,
            mult_forca REAL DEFAULT 0, mult_velocidade REAL DEFAULT 0,
            mult_resistencia REAL DEFAULT 0,
            PRIMARY KEY (user_id, potencial))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS vagas (
            nome TEXT PRIMARY KEY, categoria TEXT, multiplicador REAL DEFAULT 0, bonus_fixo INTEGER DEFAULT 0,
            role_id INTEGER, atributo TEXT DEFAULT 'todos', limite INTEGER DEFAULT 0,
            restricao_raca TEXT, vaga_id TEXT UNIQUE, descricao TEXT, bloqueada INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS player_vagas (user_id INTEGER, vaga_nome TEXT, FOREIGN KEY(vaga_nome) REFERENCES vagas(nome))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS vagas_vinculo (vaga_pai TEXT, vaga_filha TEXT, FOREIGN KEY(vaga_pai) REFERENCES vagas(nome), FOREIGN KEY(vaga_filha) REFERENCES vagas(nome), PRIMARY KEY (vaga_pai, vaga_filha))''')
        
        # Tabelas do Sistema de Perícias
        cursor.execute('''CREATE TABLE IF NOT EXISTS pericias_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, raca TEXT, 
            descricao TEXT, bonus_valor REAL, atributo_afetado TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS player_pericias (
            user_id INTEGER, pericia_id INTEGER, nivel INTEGER DEFAULT 1, pp_investido INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, pericia_id), FOREIGN KEY(pericia_id) REFERENCES pericias_base(id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS pericia_raca_heranca (
            raca_origem TEXT NOT NULL, raca_pericia TEXT NOT NULL,
            PRIMARY KEY (raca_origem, raca_pericia))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS kido_estado (
            user_id INTEGER PRIMARY KEY, reiryoku_atual INTEGER, cooldown INTEGER DEFAULT 0,
            usos_total INTEGER DEFAULT 0, gasto_total INTEGER DEFAULT 0, poder_total INTEGER DEFAULT 0,
            ultimo_kido TEXT, ultimo_poder INTEGER DEFAULT 0)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS kido_usos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, categoria TEXT, numero INTEGER,
            metodo TEXT, custo INTEGER, poder INTEGER, cooldown INTEGER, usado_em TEXT DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS kido_tecnicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, categoria TEXT, numero INTEGER,
            classificacao TEXT DEFAULT 'oficial', criador_id INTEGER, descricao TEXT, dano_bonus REAL,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tecnica_estado (
            user_id INTEGER PRIMARY KEY, cooldown INTEGER DEFAULT 0, usos_total INTEGER DEFAULT 0,
            ultimo_tecnica TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tecnica_usos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, tecnica_id INTEGER, nome TEXT,
            atributo TEXT, multiplicador REAL, bonus_fixo INTEGER, duracao INTEGER, cooldown INTEGER,
            usado_em TEXT DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tecnicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, categoria TEXT,
            classificacao TEXT DEFAULT 'oficial', criador_id INTEGER, descricao TEXT,
            multiplicador REAL DEFAULT 0, bonus_fixo INTEGER DEFAULT 0, atributo TEXT DEFAULT 'todos',
            duracao INTEGER DEFAULT 1, cooldown INTEGER DEFAULT 1,
            raca TEXT, requer_pericia TEXT, liberada INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tecnica_role_unlocks (
            tecnica_id INTEGER NOT NULL, role_id INTEGER NOT NULL,
            PRIMARY KEY (tecnica_id, role_id),
            FOREIGN KEY(tecnica_id) REFERENCES tecnicas(id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS tecnica_user_unlocks (
            tecnica_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            PRIMARY KEY (tecnica_id, user_id),
            FOREIGN KEY(tecnica_id) REFERENCES tecnicas(id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS attribute_modifiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, atributo TEXT, nome TEXT,
            tipo TEXT, valor REAL, origem TEXT DEFAULT 'manual', ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP, tecnica_uso_id INTEGER, turnos_restantes INTEGER)''')
        
        # Migrations
        columns = [
            ('potenciais', 'cooldown', 'INTEGER DEFAULT 0'),
            ('potenciais', 'custo_ativacao', 'INTEGER DEFAULT 0'),
            ('potenciais', 'custo_turno', 'INTEGER DEFAULT 0'),
            ('potenciais', 'mult_forca', 'REAL DEFAULT 0'),
            ('potenciais', 'mult_velocidade', 'REAL DEFAULT 0'),
            ('potenciais', 'mult_resistencia', 'REAL DEFAULT 0'),
            ('player_potencial', 'cooldown', 'INTEGER DEFAULT 0'),
            ('player_potencial', 'dur_mod', 'INTEGER DEFAULT 0'),
            ('player_potencial', 'cd_mod', 'INTEGER DEFAULT 0'),
            ('player_potencial', 'mult_override', 'REAL DEFAULT 0'),
            ('player_potencial', 'imagem_url', 'TEXT'),
            ('player_potencial', 'mult_forca', 'REAL DEFAULT 0'),
            ('player_potencial', 'mult_velocidade', 'REAL DEFAULT 0'),
            ('player_potencial', 'mult_resistencia', 'REAL DEFAULT 0'),
            ('vagas', 'atributo', "TEXT DEFAULT 'todos'"),
            ('vagas', 'limite', 'INTEGER DEFAULT 0'),
            ('vagas', 'restricao_raca', 'TEXT'),
            ('vagas', 'vaga_id', 'TEXT'),
            ('personagens', 'limite_nivel', 'INTEGER DEFAULT 0'),
            ('personagens', 'slots_potencial', 'INTEGER DEFAULT 1'),
            ('vagas', 'descricao', 'TEXT'),
            ('personagens', 'pontos_pericia', 'INTEGER DEFAULT 0'),
            ('personagens', 'reiryoku_atual', 'INTEGER'),
            ('kido_usos', 'tecnica_id', 'INTEGER'),
            ('kido_estado', 'ultimo_poder', 'INTEGER DEFAULT 0'),
            ('vagas', 'bloqueada', 'INTEGER DEFAULT 0'),
            ('config_pretensao', 'anunciado', 'INTEGER DEFAULT 0'),
            ('kido_tecnicas', 'criador_id', 'INTEGER'),
            ('kido_tecnicas', 'descricao', 'TEXT'),
            ('kido_tecnicas', 'dano_bonus', 'REAL'),
            ('player_pericias', 'pp_investido', 'INTEGER DEFAULT 0'),
            ('attribute_modifiers', 'tecnica_uso_id', 'INTEGER'),
            ('attribute_modifiers', 'turnos_restantes', 'INTEGER'),
            ('tecnicas', 'criador_id', 'INTEGER'),
            ('tecnicas', 'descricao', 'TEXT'),
            ('tecnicas', 'multiplicador', 'REAL DEFAULT 0'),
            ('tecnicas', 'bonus_fixo', 'INTEGER DEFAULT 0'),
            ('tecnicas', 'atributo', "TEXT DEFAULT 'todos'"),
            ('tecnicas', 'duracao', 'INTEGER DEFAULT 1'),
            ('tecnicas', 'cooldown', 'INTEGER DEFAULT 1'),
            ('tecnicas', 'raca', 'TEXT'),
            ('tecnicas', 'requer_pericia', 'TEXT'),
            ('tecnicas', 'liberada', 'INTEGER DEFAULT 1'),
            ('tecnica_usos', 'tecnica_id', 'INTEGER'),
            ('tecnica_usos', 'nome', 'TEXT'),
            ('tecnica_usos', 'atributo', 'TEXT'),
            ('tecnica_usos', 'multiplicador', 'REAL'),
            ('tecnica_usos', 'bonus_fixo', 'INTEGER'),
            ('tecnica_usos', 'duracao', 'INTEGER'),
            ('tecnica_usos', 'cooldown', 'INTEGER')
        ]
        for table, col, detail in columns:
            try: cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} {detail}')
            except sqlite3.OperationalError: pass

        cursor.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        migration_id = 'pericia_raca_heranca_defaults_20260514'
        if not cursor.execute('SELECT 1 FROM schema_migrations WHERE id = ?', (migration_id,)).fetchone():
            cursor.executemany('''
                INSERT OR IGNORE INTO pericia_raca_heranca (raca_origem, raca_pericia)
                VALUES (?, ?)
            ''', [
                ('Vaizard', 'Shinigami'),
                ('Vaizard', 'Hollow'),
                ('Vizard', 'Shinigami'),
                ('Vizard', 'Hollow'),
                ('Visored', 'Shinigami'),
                ('Visored', 'Hollow'),
            ])
            cursor.execute('INSERT INTO schema_migrations (id) VALUES (?)', (migration_id,))

        migration_id = 'reiatsu_scale_intermediate_20260514'
        if not cursor.execute('SELECT 1 FROM schema_migrations WHERE id = ?', (migration_id,)).fetchone():
            previous_scale_applied = cursor.execute(
                'SELECT 1 FROM schema_migrations WHERE id = ?',
                ('reiatsu_scale_20260514',),
            ).fetchone()
            if previous_scale_applied:
                cursor.execute('''
                    UPDATE personagens
                    SET limite_nivel = CASE limite_nivel
                        WHEN 0 THEN 0
                        WHEN 1 THEN 1
                        WHEN 2 THEN 2
                        WHEN 3 THEN 3
                        WHEN 4 THEN 4
                        WHEN 5 THEN 6
                        WHEN 6 THEN 7
                        WHEN 7 THEN 8
                        WHEN 8 THEN 9
                        WHEN 9 THEN 10
                        WHEN 10 THEN 10
                        WHEN 11 THEN 11
                        WHEN 12 THEN 12
                        WHEN 13 THEN 12
                        WHEN 14 THEN 13
                        WHEN 15 THEN 14
                        WHEN 16 THEN 16
                        WHEN 17 THEN 18
                        WHEN 18 THEN 20
                        ELSE limite_nivel
                    END
                ''')
            else:
                cursor.execute('''
                    UPDATE personagens
                    SET limite_nivel = CASE limite_nivel
                        WHEN 0 THEN 0
                        WHEN 1 THEN 2
                        WHEN 2 THEN 4
                        WHEN 3 THEN 6
                        WHEN 4 THEN 8
                        WHEN 5 THEN 10
                        WHEN 6 THEN 12
                        WHEN 7 THEN 14
                        WHEN 8 THEN 16
                        WHEN 9 THEN 18
                        WHEN 10 THEN 20
                        ELSE limite_nivel
                    END
                ''')
            cursor.execute('INSERT INTO schema_migrations (id) VALUES (?)', (migration_id,))

        migration_id = 'reiatsu_scale_expanded_20260514'
        if not cursor.execute('SELECT 1 FROM schema_migrations WHERE id = ?', (migration_id,)).fetchone():
            # Preserva o teto anterior escolhendo o primeiro nível novo >= ao teto antigo.
            cursor.execute('''
                UPDATE personagens
                SET limite_nivel = CASE limite_nivel
                    WHEN 0 THEN 3
                    WHEN 1 THEN 8
                    WHEN 2 THEN 10
                    WHEN 3 THEN 12
                    WHEN 4 THEN 13
                    WHEN 5 THEN 14
                    WHEN 6 THEN 15
                    WHEN 7 THEN 18
                    WHEN 8 THEN 19
                    WHEN 9 THEN 23
                    WHEN 10 THEN 26
                    WHEN 11 THEN 30
                    WHEN 12 THEN 33
                    WHEN 13 THEN 35
                    WHEN 14 THEN 36
                    WHEN 15 THEN 37
                    WHEN 16 THEN 38
                    WHEN 17 THEN 39
                    WHEN 18 THEN 41
                    WHEN 19 THEN 41
                    WHEN 20 THEN 41
                    ELSE limite_nivel
                END
            ''')
            cursor.execute('INSERT INTO schema_migrations (id) VALUES (?)', (migration_id,))

        migration_id = 'reiatsu_scale_levels_20260514'
        if not cursor.execute('SELECT 1 FROM schema_migrations WHERE id = ?', (migration_id,)).fetchone():
            # Converte a escala de 42 níveis para a escala atual de 15 níveis preservando o teto.
            cursor.execute('''
                UPDATE personagens
                SET limite_nivel = CASE limite_nivel
                    WHEN 0 THEN 0
                    WHEN 1 THEN 0
                    WHEN 2 THEN 0
                    WHEN 3 THEN 0
                    WHEN 4 THEN 0
                    WHEN 5 THEN 0
                    WHEN 6 THEN 1
                    WHEN 7 THEN 1
                    WHEN 8 THEN 1
                    WHEN 9 THEN 1
                    WHEN 10 THEN 1
                    WHEN 11 THEN 2
                    WHEN 12 THEN 2
                    WHEN 13 THEN 2
                    WHEN 14 THEN 2
                    WHEN 15 THEN 2
                    WHEN 16 THEN 3
                    WHEN 17 THEN 3
                    WHEN 18 THEN 3
                    WHEN 19 THEN 3
                    WHEN 20 THEN 3
                    WHEN 21 THEN 4
                    WHEN 22 THEN 4
                    WHEN 23 THEN 4
                    WHEN 24 THEN 4
                    WHEN 25 THEN 5
                    WHEN 26 THEN 5
                    WHEN 27 THEN 5
                    WHEN 28 THEN 5
                    WHEN 29 THEN 6
                    WHEN 30 THEN 6
                    WHEN 31 THEN 6
                    WHEN 32 THEN 6
                    WHEN 33 THEN 7
                    WHEN 34 THEN 7
                    WHEN 35 THEN 7
                    WHEN 36 THEN 7
                    WHEN 37 THEN 8
                    WHEN 38 THEN 8
                    WHEN 39 THEN 8
                    WHEN 40 THEN 8
                    WHEN 41 THEN 8
                    ELSE limite_nivel
                END
            ''')
            cursor.execute('INSERT INTO schema_migrations (id) VALUES (?)', (migration_id,))

        migration_id = 'reiatsu_scale_spiritual_power_20260514'
        if not cursor.execute('SELECT 1 FROM schema_migrations WHERE id = ?', (migration_id,)).fetchone():
            # Converte a escala de 15 níveis para a métrica de 6 faixas preservando o teto.
            cursor.execute('''
                UPDATE personagens
                SET limite_nivel = CASE limite_nivel
                    WHEN 0 THEN 0
                    WHEN 1 THEN 0
                    WHEN 2 THEN 0
                    WHEN 3 THEN 0
                    WHEN 4 THEN 0
                    WHEN 5 THEN 1
                    WHEN 6 THEN 1
                    WHEN 7 THEN 1
                    WHEN 8 THEN 2
                    WHEN 9 THEN 2
                    WHEN 10 THEN 2
                    WHEN 11 THEN 2
                    WHEN 12 THEN 3
                    WHEN 13 THEN 3
                    WHEN 14 THEN 3
                    ELSE limite_nivel
                END
            ''')
            cursor.execute('INSERT INTO schema_migrations (id) VALUES (?)', (migration_id,))

        _upsert_default_vagas(cursor)
        _upsert_default_pericias(cursor)
        _upsert_default_tecnicas(cursor)

        cursor.execute('''
            INSERT INTO pericias_base (nome, raca, descricao, bonus_valor, atributo_afetado)
            SELECT 'Kidō', 'Todas',
                   'Domínio de feitiços espirituais: Hadō, Bakudō e Kaidō. Define acesso, gasto, estabilidade e poder dos Kidō.',
                   0.02, 'kido'
            WHERE NOT EXISTS (
                SELECT 1 FROM pericias_base WHERE LOWER(REPLACE(nome, 'ō', 'o')) = 'kido'
            )
        ''')

        oficiais = [
            ('Shō', 'Hadō', 1, 'Empurra o alvo com força espiritual.'),
            ('Byakurai', 'Hadō', 4, 'Dispara um relâmpago branco concentrado.'),
            ('Tsuzuri Raiden', 'Hadō', 11, 'Conduz eletricidade por um objeto ou contato.'),
            ('Fushibi', 'Hadō', 12, 'Cria uma rede de energia explosiva que pode ser combinada com outros Hadō.'),
            ('Shakkahō', 'Hadō', 31, 'Dispara uma esfera de energia vermelha explosiva.'),
            ('Ōkasen', 'Hadō', 32, 'Lança uma onda larga de energia amarela.'),
            ('Sōkatsui', 'Hadō', 33, 'Dispara energia azul em área frontal.'),
            ('Haien', 'Hadō', 54, 'Consome o alvo com chamas espirituais.'),
            ("Daichi Ten'yō", 'Hadō', 57, 'Ergue e arremessa massas de terreno com pressão espiritual.'),
            ('Tenran', 'Hadō', 58, 'Cria um tornado de energia.'),
            ('Raikōhō', 'Hadō', 63, 'Dispara uma rajada elétrica destrutiva.'),
            ('Sōren Sōkatsui', 'Hadō', 73, 'Versão dupla e ampliada do Sōkatsui.'),
            ('Zangerin', 'Hadō', 78, 'Libera uma lâmina ou onda cortante de energia espiritual.'),
            ('Hiryū Gekizoku Shinten Raihō', 'Hadō', 88, 'Canhão espiritual de alto impacto.'),
            ('Kurohitsugi', 'Hadō', 90, 'Envolve o alvo em uma caixa negra destrutiva.'),
            ('Senjū Kōten Taihō', 'Hadō', 91, 'Invoca múltiplas lanças de energia.'),
            ('Goryūtenmetsu', 'Hadō', 99, 'Invoca dragões de energia destrutiva.'),
            ('Gaki Rekkō', 'Hadō', 99, 'Dispara múltiplos projéteis de energia verde em sequência.'),
            ('Hyōga Seiran', 'Hadō', 99, 'Libera uma grande onda congelante de energia espiritual.'),
            ('Kongōbaku', 'Hadō', 99, 'Cria uma explosão massiva de energia espiritual.'),
            ('Jūgeki Byakurai', 'Hadō', 99, 'Variação modificada de Byakurai com perfuração reforçada.'),
            ('Sai', 'Bakudō', 1, 'Prende os braços do alvo atrás das costas.'),
            ('Hainawa', 'Bakudō', 4, 'Cria uma corda espiritual para imobilizar.'),
            ('Seki', 'Bakudō', 8, 'Cria um escudo repelente.'),
            ('Geki', 'Bakudō', 9, 'Paralisa o alvo com luz vermelha.'),
            ('Hōrin', 'Bakudō', 9, 'Cria uma corda de energia controlável.'),
            ('Sekienton', 'Bakudō', 21, 'Cria fumaça vermelha para fuga ou ocultação.'),
            ('Kyokkō', 'Bakudō', 26, 'Oculta presença e Reiatsu.'),
            ('Shitotsu Sansen', 'Bakudō', 30, 'Prende o alvo com três lâminas de luz.'),
            ('Tsuriboshi', 'Bakudō', 37, 'Cria uma rede espiritual de sustentação.'),
            ('Enkōsen', 'Bakudō', 39, 'Cria um escudo circular de energia.'),
            ('Kakushitsuijaku', 'Bakudō', 58, 'Rastreia localização espiritual.'),
            ('Rikujōkōrō', 'Bakudō', 61, 'Prende o alvo com seis hastes de luz.'),
            ('Hyapporankan', 'Bakudō', 62, 'Dispara hastes espirituais para conter o alvo.'),
            ('Sajō Sabaku', 'Bakudō', 63, 'Envolve o alvo com correntes espirituais.'),
            ('Tozanshō', 'Bakudō', 73, 'Cria uma barreira piramidal invertida.'),
            ('Gochūtekkan', 'Bakudō', 75, 'Prende o alvo com cinco pilares.'),
            ('Tenteikūra', 'Bakudō', 77, 'Transmite mensagens espirituais.'),
            ('Kuyō Shibari', 'Bakudō', 79, 'Prende o alvo com nove pontos de energia.'),
            ('Dankū', 'Bakudō', 81, 'Cria uma parede defensiva de energia.'),
            ('Kin', 'Bakudō', 99, 'Primeira parte de uma contenção avançada.'),
            ('Bankin', 'Bakudō', 99, 'Segunda parte de uma contenção avançada.'),
            ('Kyōmon', 'Barreira', 99, 'Cria uma barreira resistente a ataques externos, mas vulnerável por dentro.'),
            ('Hachigyō Sōgai', 'Barreira', 99, 'Barreira avançada usada para conter ou isolar uma área.'),
            ('Shijū Saimon', 'Barreira', 99, 'Conjunto de quatro portões/barreiras de contenção espiritual.'),
        ]
        for nome, categoria, numero, descricao in oficiais:
            cursor.execute('''
                INSERT INTO kido_tecnicas (nome, categoria, numero, classificacao, descricao)
                SELECT ?, ?, ?, 'oficial', ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM kido_tecnicas
                    WHERE nome = ? AND categoria = ? AND numero = ? AND classificacao = 'oficial'
                )
            ''', (nome, categoria, numero, descricao, nome, categoria, numero))

        cursor.execute("""
            UPDATE kido_tecnicas
            SET classificacao = 'proibido'
            WHERE nome = 'Ittō Kasō' AND classificacao = 'oficial'
        """)

        cursor.execute("""
            UPDATE kido_tecnicas
            SET classificacao = 'exclusivo'
            WHERE nome IN ('Kurohitsugi', 'Senjū Kōten Taihō', 'Goryūtenmetsu')
              AND classificacao = 'oficial'
        """)

        proibidos = [
            ('Ittō Kasō', 'Hadō', 96, 'Hadō sacrificial proibido que usa o próprio corpo como catalisador.'),
            ('Jikanteishi', 'Kidō Proibido', 99, 'Feitiço proibido de estase temporal que interrompe o tempo numa área.'),
            ("Kūkanten'i", 'Kidō Proibido', 99, 'Feitiço proibido de deslocamento espacial que transfere uma porção de espaço.'),
        ]
        for nome, categoria, numero, descricao in proibidos:
            cursor.execute('''
                INSERT INTO kido_tecnicas (nome, categoria, numero, classificacao, descricao)
                SELECT ?, ?, ?, 'proibido', ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM kido_tecnicas
                    WHERE nome = ? AND classificacao = 'proibido'
                )
            ''', (nome, categoria, numero, descricao, nome))

        exclusivos = [
            ('Kurohitsugi', 'Hadō', 90, 'Kidō de alto nível associado a usuários excepcionais; sela o alvo num caixão negro de energia que o lacera.'),
            ('Senjū Kōten Taihō', 'Hadō', 91, 'Técnica devastadora que forma múltiplos pontos de energia e os dispara contra o alvo.'),
            ('Goryūtenmetsu', 'Hadō', 99, 'Hadō de altíssimo nível associado a maestria extrema, manifestando dragões de energia destrutiva.'),
        ]
        for nome, categoria, numero, descricao in exclusivos:
            cursor.execute('''
                INSERT INTO kido_tecnicas (nome, categoria, numero, classificacao, descricao)
                SELECT ?, ?, ?, 'exclusivo', ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM kido_tecnicas
                    WHERE nome = ? AND classificacao = 'exclusivo'
                )
            ''', (nome, categoria, numero, descricao, nome))
        
        conn.commit()

def setar_canal_logs(canal_id):
    with get_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO config_logs (id, canal_logs) VALUES (1, ?)', (canal_id,))
        conn.commit()

def setar_canal_historico(canal_id):
    with get_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO config_historico (id, canal_historico) VALUES (1, ?)', (canal_id,))
        conn.commit()

def setar_canal_comandos(canal_id):
    with get_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO config_comandos (id, canal_id) VALUES (1, ?)', (canal_id,))
        conn.commit()

def bloquear_canal_bot(canal_id):
    with get_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO canais_bloqueados_bot (canal_id) VALUES (?)', (canal_id,))
        conn.commit()

def liberar_canal_bot(canal_id):
    with get_connection() as conn:
        conn.execute('DELETE FROM canais_bloqueados_bot WHERE canal_id = ?', (canal_id,))
        conn.commit()

def canal_bot_bloqueado(canal_id):
    with get_connection() as conn:
        res = conn.execute('SELECT 1 FROM canais_bloqueados_bot WHERE canal_id = ?', (canal_id,)).fetchone()
        return bool(res)

def listar_canais_bloqueados_bot():
    with get_connection() as conn:
        return [row[0] for row in conn.execute('SELECT canal_id FROM canais_bloqueados_bot ORDER BY canal_id').fetchall()]

def get_canal_logs():
    with get_connection() as conn:
        res = conn.execute('SELECT canal_logs FROM config_logs WHERE id = 1').fetchone()
        return res[0] if res else None

def get_canal_historico():
    with get_connection() as conn:
        res = conn.execute('SELECT canal_historico FROM config_historico WHERE id = 1').fetchone()
        return res[0] if res else None

def get_canal_comandos():
    with get_connection() as conn:
        res = conn.execute('SELECT canal_id FROM config_comandos WHERE id = 1').fetchone()
        return res[0] if res else None

def get_config_pretensao():
    with get_connection() as conn:
        return conn.execute('SELECT canal_id, hora_abrir, hora_fechar, dias_semana FROM config_pretensao WHERE id = 1').fetchone()

def set_config_pretensao_canal(canal_id):
    with get_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO config_pretensao (id) VALUES (1)')
        conn.execute('UPDATE config_pretensao SET canal_id = ? WHERE id = 1', (canal_id,))
        conn.commit()

def set_config_pretensao_horarios(hora_abrir, hora_fechar, dias_semana):
    with get_connection() as conn:
        conn.execute('INSERT OR IGNORE INTO config_pretensao (id) VALUES (1)')
        conn.execute(
            '''
            UPDATE config_pretensao
            SET hora_abrir = ?, hora_fechar = ?, dias_semana = ?
            WHERE id = 1
            ''',
            (hora_abrir, hora_fechar, dias_semana)
        )
        conn.commit()

def get_vagas_bonus(user_id):
    with get_connection() as conn:
        res = conn.execute('''
            SELECT v.multiplicador, v.bonus_fixo, v.atributo
            FROM player_vagas pv JOIN vagas v ON pv.vaga_nome = v.nome 
            WHERE pv.user_id = ?
        ''', (user_id,)).fetchall()
    
    bonuses = {k: {'mult': 0.0, 'fixo': 0} for k in ['forca', 'velocidade', 'resistencia']}
    for mult, fixo, attr_str in res:
        targets = [a.strip().lower() for a in attr_str.replace('+', ',').split(',')]
        for k in bonuses:
            if 'todos' in targets or k in targets:
                bonuses[k]['mult'] += mult
                bonuses[k]['fixo'] += fixo
    return bonuses


def _split_bonus_targets(attr_str):
    normalized = unicodedata.normalize('NFKD', attr_str or '')
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii').casefold()
    raw_targets = ascii_text.replace('+', ',').split(',')
    targets = []
    for raw in raw_targets:
        target = raw.strip()
        if not target:
            continue
        if target.startswith('tecnica:') or target.startswith('turnos:'):
            continue
        if target in ('todos', 'todas', 'fisicos', 'fisicas'):
            for physical in ('forca', 'velocidade', 'resistencia'):
                if physical not in targets:
                    targets.append(physical)
            continue
        if target not in targets:
            targets.append(target)
    return targets

def get_pericia_bonuses(user_id):
    with get_connection() as conn:
        res = conn.execute('''
            SELECT pb.atributo_afetado, pb.bonus_valor, pp.nivel
            FROM player_pericias pp 
            JOIN pericias_base pb ON pp.pericia_id = pb.id
            WHERE pp.user_id = ?
        ''', (user_id,)).fetchall()
    
    bonuses = {'forca': 0.0, 'velocidade': 0.0, 'resistencia': 0.0, 'reiryoku': 0.0, 'reiatsu': 0.0, 'kido': 0.0}
    for attr, valor, nivel in res:
        if valor is None:
            continue
        for target in _split_bonus_targets(attr):
            if target in bonuses:
                bonuses[target] += (valor * (nivel - 1)) # Nível 1 não dá bônus, apenas a partir do 2
    return bonuses
