"""Contacts of a 2GIS card: every contact kept, labels as in 2GIS (or a default), the owner first."""
from leadbombing.leads.contacts import business_contacts, contact_book, contacts_of, reach_of
from leadbombing.leads.firm import owner_of_ip


def _item(*groups):
    return {'contact_groups': [dict(g) for g in groups]}


def _group(*contacts, name=None, comment=None):
    group = {'contacts': list(contacts)}
    if name:
        group['name'] = name
    if comment:
        group['comment'] = comment
    return group


def _reach(item):
    return reach_of(contacts_of(item), contact_book(item, 'для записи'))


def test_book_keeps_every_contact_type():
    # Arrange
    item = _item(_group(
        {'type': 'phone', 'value': '+74951112233'},
        {'type': 'fax', 'value': '+74951112234'},
        {'type': 'viber', 'url': 'viber://chat?number=79991112233'},
        {'type': 'max', 'url': 'https://max.ru/u/firm'},
        {'type': 'instagram', 'url': 'https://instagram.com/firm?utm=1'},
        {'type': 'odnoklassniki', 'url': 'https://ok.ru/firm'},
        {'type': 'skype', 'value': 'firm.skype'},
        {'type': 'rutube', 'url': 'https://rutube.ru/firm'},
    ))

    # Act
    book = contact_book(item, 'для записи')

    # Assert
    assert [c['type'] for c in book] == ['phone', 'fax', 'viber', 'max', 'instagram', 'odnoklassniki', 'skype', 'rutube']
    assert [c['title'] for c in book] == ['Телефон', 'Факс', 'Viber', 'MAX', 'Instagram', 'Одноклассники', 'Skype',
                                          'Прочее (rutube)']
    assert book[0]['value'] == '+7 495 111-22-33' and book[0]['href'] == 'tel:+74951112233'
    assert book[4]['value'] == 'https://instagram.com/firm' and book[4]['href'] == 'https://instagram.com/firm'
    assert book[3]['label'] == 'для записи' and book[6]['href'] is None


def test_labels_come_from_group_name_and_comments():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+74951112233', 'comment': 'администратор'},
                        name='Сервисный центр', comment='Многоканальный'))

    # Act
    [phone] = contact_book(item, 'для записи')

    # Assert
    assert phone['label'] == 'Сервисный центр · Многоканальный · администратор'
    assert phone['label_source'] == '2gis' and phone['role'] == 'general'


def test_default_labels_by_contact_type_and_sphere():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+74951112233'},
                        {'type': 'telegram', 'url': 'https://t.me/firm'},
                        {'type': 'vkontakte', 'url': 'https://vk.com/firm'},
                        {'type': 'website', 'url': 'https://firm.ru'},
                        {'type': 'email', 'value': 'a@firm.ru'}))

    # Act
    book = contact_book(item, 'для бронирования')

    # Assert
    assert [c['label'] for c in book] == ['для бронирования', 'для бронирования', 'страница фирмы', 'сайт фирмы',
                                          'почта фирмы']
    assert {c['label_source'] for c in book} == {'default'}


def test_messenger_on_a_labelled_number_gets_the_phone_label():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+79161234567', 'comment': 'Директор'}),
                 _group({'type': 'whatsapp', 'url': 'https://wa.me/79161234567'}))

    # Act
    book = contact_book(item, 'для записи')

    # Assert
    assert [(c['type'], c['label'], c['role']) for c in book] == [
        ('phone', 'Директор', 'owner'), ('whatsapp', 'Директор', 'owner')]
    assert book[1]['label_source'] == 'phone'


def test_roles_and_owner_first():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+74950000001'}, name='Бухгалтерия'),
                 _group({'type': 'phone', 'value': '+74950000002'}, name='Отдел бронирования'),
                 _group({'type': 'phone', 'value': '+74950000003'}),
                 _group({'type': 'phone', 'value': '+74950000004', 'comment': 'владелец'}))

    # Act
    book = contact_book(item, 'для записи')

    # Assert
    assert [c['role'] for c in book] == ['owner', 'general', 'booking', 'department']
    assert book[0]['value'] == '+7 495 000-00-04'


def test_same_number_in_two_groups_is_one_row_with_both_labels():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+74950000001'}, name='Ресепшен'),
                 _group({'type': 'phone', 'value': '84950000001'}, name='Директор'))

    # Act
    book = contact_book(item, 'для записи')

    # Assert
    assert len(book) == 1 and book[0]['label'] == 'Ресепшен; Директор' and book[0]['role'] == 'owner'


def test_owner_city_phone_beats_admin_whatsapp():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+79161234567'},
                        {'type': 'whatsapp', 'url': 'https://wa.me/79161234567'}, name='Администратор'),
                 _group({'type': 'phone', 'value': '+74951112233'}, name='Руководитель'))

    # Act
    reach = _reach(item)

    # Assert
    assert (reach.write_first, reach.write_here) == ('phone', '+7 495 111-22-33')
    assert reach.main_phone == '+7 495 111-22-33'


def test_general_number_beats_accounting_whatsapp():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+79161234567'},
                        {'type': 'whatsapp', 'url': 'https://wa.me/79161234567'}, name='Бухгалтерия'),
                 _group({'type': 'phone', 'value': '+74951112233'}))

    # Act
    reach = _reach(item)

    # Assert
    assert reach.write_here == '+7 495 111-22-33' and reach.channel == 'Звонок (городской)'


def test_unlabelled_contacts_keep_the_old_order():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+74951112233'}, {'type': 'phone', 'value': '+79161234567'},
                        {'type': 'telegram', 'url': 'https://t.me/firm'},
                        {'type': 'whatsapp', 'url': 'https://wa.me/79161234567?text=hi'}))

    # Act
    reach = _reach(item)

    # Assert
    assert (reach.write_first, reach.write_here) == ('whatsapp', 'https://wa.me/79161234567')
    assert reach.main_phone == '+7 916 123-45-67' and reach.public_phone == '+7 916 123-45-67'


def test_demo_page_never_gets_the_owner_number():
    # Arrange
    item = _item(_group({'type': 'phone', 'value': '+79161234567'},
                        {'type': 'whatsapp', 'url': 'https://wa.me/79161234567'}, name='Директор'),
                 _group({'type': 'phone', 'value': '+74951112233'}))
    c = contacts_of(item)

    # Act
    reach = reach_of(c, contact_book(item, 'для записи'))
    contacts = business_contacts(reach, c, 'Москва', {}, with_website=False)

    # Assert
    assert reach.write_here == 'https://wa.me/79161234567'
    assert contacts['phone'] == '+7 495 111-22-33' and 'whatsapp' not in contacts


def test_owner_of_ip():
    assert owner_of_ip('ИП Иванов Иван Иванович') == 'Иванов Иван Иванович'
    assert owner_of_ip('Индивидуальный предприниматель Петрова Анна') == 'Петрова Анна'
    assert owner_of_ip('ИП  Сидоров  Пётр  Ильич ') == 'Сидоров Пётр Ильич'
    assert owner_of_ip('ООО Усадьба') is None
    assert owner_of_ip('') is None and owner_of_ip(None) is None
