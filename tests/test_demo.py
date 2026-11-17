from leadbombing.leads.demo import amenities_description, legal_block, wordmark_main


def test_wordmark_main_cuts_long_names_on_a_word():
    assert wordmark_main('Хлебниковские бани') == 'Хлебниковские бани'
    assert wordmark_main('Банный комплекс Северное сияние') == 'Банный комплекс'
    assert wordmark_main('Оченьдлинноеназваниебезпробелов') == 'Оченьдлинноеназвание'  # no space: hard cut at 20


def test_amenities_description_and_legal_stub():
    assert amenities_description(['парковка', 'Wi-Fi']) == 'Парковка, wi-fi.'
    assert amenities_description([]) == ''
    assert legal_block(None)['operator_name'] == 'ЗАГЛУШКА: оператор ПДн'
