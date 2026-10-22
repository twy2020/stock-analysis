import pytest
import respx
from httpx import Response
from app.extensions import database
from app.models import Message, MessageCitation, User
from test_chat import sign_in, configure_dependencies


@pytest.mark.parametrize('suffix,payload', [
    ('pages', {'pageCount': 12}),
    ('pages/3', {'pageNumber': 3, 'textItems': []}),
    ('pages/3/image', b'\xff\xd8\xffimage'),
])
@respx.mock
def test_page_images_require_owned_citation_and_proxy_content(app, client, suffix, payload):
    route = '/api/v1/evidence/query/citation/' + suffix
    assert client.get(route).status_code == 401
    csrf = sign_in(client)
    configure_dependencies(app)
    assert client.get(route).status_code == 404
    conversation = client.post('/api/v1/conversations', json={'title': 'Pages', 'knowledgeBaseId': 'kb'},
                               headers={'X-CSRF-Token': csrf}).json
    with app.app_context():
        user = database.session.query(User).filter_by(username='admin').one()
        message = Message(conversation_id=conversation['id'], organization_id=user.organization_id,
                          owner_id=user.id, role='assistant', content='', status='COMPLETED')
        database.session.add(message)
        database.session.flush()
        database.session.add(MessageCitation(message_id=message.id, label=1, query_id='query', citation_id='citation',
            document_id='d', document_version_id='v', title='PDF', file_name='source.pdf', media_type='application/pdf',
            passage='text', retrieval_mode='hybrid'))
        database.session.commit()
    upstream = respx.get('https://rag.example/api/v1/consumer/queries/query/citations/citation/' + suffix)
    upstream.mock(return_value=Response(200, content=payload, headers={'Content-Type': 'image/jpeg'})
                  if isinstance(payload, bytes) else Response(200, json=payload))
    response = client.get(route)
    assert response.status_code == 200
    assert (response.data if isinstance(payload, bytes) else response.json) == payload
    if isinstance(payload, bytes):
        assert response.content_type == 'image/jpeg'
    else:
        upstream.mock(return_value=Response(202, json={'status': 'PREPARING'}))
        assert client.get(route).json == {'status': 'PREPARING'}
    with app.app_context():
        database.session.query(MessageCitation).delete()
        database.session.commit()
    assert client.get(route).status_code == 404
