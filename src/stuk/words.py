"""Original, compact word pools for quiet, offline practice."""

import random

RU_WORDS: tuple[str, ...] = tuple(
    """
    утро вечер день ночь свет тень воздух ветер небо облако дождь снег
    солнце луна звезда море река озеро берег волна лес поле луг сад
    дерево лист ветка корень трава цветок мох камень песок земля тропа
    дорога город улица площадь мост окно дверь дом крыша стена комната
    стол стул книга письмо строка слово буква голос звук ритм тишина
    покой тепло холод время минута час миг память мысль мечта взгляд
    улыбка рука ладонь плечо шаг след путь даль круг линия точка край
    начало конец место встреча разговор вопрос ответ смысл дело выбор
    жизнь друг люди семья работа отдых прогулка поезд билет карта ключ
    чашка чай кофе хлеб яблоко груша мёд вода вкус запах цвет ткань
    бумага карандаш чернила лампа полка кресло плед зеркало стекло парус
    объём объятие экран эхо
    енот нос тон она он нота сено тесто рост
    остров лодка птица крыло гнездо кот сон огонь искра дым ручей роса
    тихий ясный тёплый мягкий лёгкий новый старый добрый тонкий чистый
    простой ровный близкий далёкий первый синий белый серый золотой
    идти видеть слышать читать писать дышать помнить думать искать
    найти ждать знать любить жить спать плыть лететь расти беречь
    рядом снова здесь там вдали утром вечером медленно быстро вместе
    всегда иногда сейчас потом ещё уже лишь почти немного долго
    """.split()
)

EN_WORDS: tuple[str, ...] = tuple(
    """
    morning evening day night light shade air wind sky cloud rain snow
    sun moon star sea river lake shore wave forest field meadow garden
    tree leaf branch root grass flower moss stone sand earth path road
    city street square bridge window door home roof wall room table
    chair book letter line word sound voice rhythm silence calm warmth
    cold time minute hour moment memory thought dream glance smile
    hand palm shoulder step trail way distance circle point edge start
    end place meeting talk question answer meaning work choice life
    friend people family rest travel train ticket map key cup tea coffee
    bread apple pear honey water taste scent color cloth paper pencil
    ink lamp shelf blanket mirror glass sail island boat bird wing nest
    cat sleep fire spark smoke stream dew quiet clear warm soft gentle
    joy june fox box haze zero
    tin tie ten nine rate tear
    new old kind thin clean simple even near far first blue white grey
    gold green silver amber small slow still bright open deep fresh
    walk see hear read write breathe remember think seek find wait
    know love live float fly grow keep hold turn watch listen learn
    make build draw share bring leave carry follow return begin stay
    again here there away slowly quickly together always sometimes
    now later almost little long under over after before between
    """.split()
)


def generate_text(
    language: str = "ru", count: int = 25, rng: random.Random | None = None
) -> str:
    """Choose 1–60 words without adjacent duplicates; an RNG makes runs repeatable."""
    if language not in ("ru", "en"):
        raise ValueError("Language must be 'ru' or 'en'.")
    if type(count) is not int or not 1 <= count <= 60:
        raise ValueError("Word count must be an integer between 1 and 60.")
    pool = RU_WORDS if language == "ru" else EN_WORDS
    chooser = rng if rng is not None else random.Random()
    words: list[str] = []
    for _ in range(count):
        candidates = (
            pool if not words else tuple(word for word in pool if word != words[-1])
        )
        words.append(chooser.choice(candidates))
    return " ".join(words)
