import json
from sqlalchemy import Column, Integer, String

from .test_base import Base, BaseTestCase
from .test_fixtures import Character

from .resource import CollectionResource, SingleResource

catchphrases = {
    'Oliver':   'You have failed this city',
    'Cisco':    "OK, you don't get to pick the names",
}


class CharacterCollectionResource(CollectionResource):
    model = Character
    resource_meta = {
        'catchphrase':  lambda resource: catchphrases.get(resource.name, None)
    }

class CharacterResource(SingleResource):
    model = Character
    meta = {
        'catchphrase':  lambda resource: catchphrases.get(resource.name, None)
    }


class MetaTest(BaseTestCase):
    def create_test_resources(self):
        self.app.add_route('/characters', CharacterCollectionResource(self.db_engine))
        self.app.add_route('/characters/{id}', CharacterResource(self.db_engine))

    def create_common_fixtures(self):
        response, = self.simulate_request('/characters', method='POST', body=json.dumps({'id': 1, 'name': 'Barry'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        response, = self.simulate_request('/characters', method='POST', body=json.dumps({'id': 2, 'name': 'Oliver'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        response, = self.simulate_request('/characters', method='POST', body=json.dumps({'id': 3, 'name': 'Caitlin'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        response, = self.simulate_request('/characters', method='POST', body=json.dumps({'id': 4, 'name': 'Cisco'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})


    def test_meta(self):
        response, = self.simulate_request('/characters/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'Barry', 'team_id': None}, 'meta': {'catchphrase': None}
        })

        response, = self.simulate_request('/characters/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Oliver', 'team_id': None}, 'meta': {'catchphrase': 'You have failed this city'}
        })

        response, = self.simulate_request('/characters/3', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'name': 'Caitlin', 'team_id': None}, 'meta': {'catchphrase': None}
        })

        response, = self.simulate_request('/characters/4', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 4, 'name': 'Cisco', 'team_id': None}, 'meta': {'catchphrase': "OK, you don't get to pick the names"}
        })

        response, = self.simulate_request('/characters', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Barry', 'team_id': None, 'meta': {'catchphrase': None}},
                {'id': 2, 'name': 'Oliver', 'team_id': None, 'meta': {'catchphrase': 'You have failed this city'}},
                {'id': 3, 'name': 'Caitlin', 'team_id': None, 'meta': {'catchphrase': None}},
                {'id': 4, 'name': 'Cisco', 'team_id': None, 'meta': {'catchphrase': "OK, you don't get to pick the names"}},
            ]
        })
