import json
from sqlalchemy import Column, Integer, String, func

from .test_base import Base, BaseTestCase
from .test_fixtures import Character, Team

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

class ExtendedCharacterCollectionResource(CollectionResource):
    model = Character
    resource_meta = {
        'catchphrase':  lambda resource, team_name: catchphrases.get(resource.name, None),
        'team_name':    lambda resource, team_name: team_name,
    }
    extra_select = [Team.name]

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query.join(Team)

class ExtendedCharacterResource(SingleResource):
    model = Character
    meta = {
        'catchphrase':  lambda resource, team_name: catchphrases.get(resource.name, None),
        'team_name':    lambda resource, team_name: team_name,
    }
    extra_select = [Team.name]

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query.join(Team)

class TeamCollectionResource(CollectionResource):
    model = Team
    resource_meta = {
        'team_size': lambda resource, team_size: team_size,
    }
    extra_select = [func.count(Character.id)]

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query.join(Character).group_by(Team.id)

class TeamResource(SingleResource):
    model = Team
    meta = {
        'team_size': lambda resource, team_size: team_size,
    }
    extra_select = [func.count(Character.id)]

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query.join(Character).group_by(Team.id)

class DynamicTeamCollectionResource(CollectionResource):
    model = Team
    def resource_meta(self, req, resp, resource, team_size, *args, **kwargs):
        if ('id' in kwargs and kwargs['id'] == 1) or req.get_param('__without_size'):
            return None
        else:
            return {
                'team_size': team_size,
            }
    extra_select = [func.count(Character.id)]

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query.join(Character).group_by(Team.id)

class DynamicTeamResource(SingleResource):
    model = Team
    def meta(self, req, resp, resource, team_size, *args, **kwargs):
        if req.get_param('__without_size'):
            return None
        else:
            return {
                'team_size': team_size,
            }
    extra_select = [func.count(Character.id)]

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query.join(Character).group_by(Team.id)

class DynamicTeamNoSizeCollectionResource(CollectionResource):
    model = Team
    def resource_meta(self, req, resp, resource, *args, **kwargs):
        return {
            'state': 'busy'
        }

class DynamicTeamNoSizeResource(SingleResource):
    model = Team
    def meta(self, req, resp, resource, *args, **kwargs):
        return {
            'state': 'busy'
        }


class MetaTest(BaseTestCase):
    def create_test_resources(self):
        self.app.add_route('/characters', CharacterCollectionResource(self.db_engine))
        self.app.add_route('/characters/{id}', CharacterResource(self.db_engine))

        self.app.add_route('/extended-characters', ExtendedCharacterCollectionResource(self.db_engine))
        self.app.add_route('/extended-characters/{id}', ExtendedCharacterResource(self.db_engine))

        self.app.add_route('/teams', TeamCollectionResource(self.db_engine))
        self.app.add_route('/teams/{id}', TeamResource(self.db_engine))

        self.app.add_route('/dynamic-teams', DynamicTeamCollectionResource(self.db_engine))
        self.app.add_route('/dynamic-teams/{id}', DynamicTeamResource(self.db_engine))

        self.app.add_route('/dynamic-teams-without-size', DynamicTeamNoSizeCollectionResource(self.db_engine))
        self.app.add_route('/dynamic-teams-without-size/{id}', DynamicTeamNoSizeResource(self.db_engine))

    def create_common_fixtures(self):
        team_flash = Team(id=1, name="Team Flash")
        team_arrow = Team(id=2, name="Team Arrow")
        self.db_session.add(team_flash)
        self.db_session.add(team_arrow)
        barry = Character(id=1, name='Barry', team=team_flash)
        oliver = Character(id=2, name='Oliver', team=team_arrow)
        caitlin = Character(id=3, name='Caitlin', team=team_flash)
        cisco = Character(id=4, name='Cisco', team=team_flash)
        self.db_session.add(barry)
        self.db_session.add(oliver)
        self.db_session.add(caitlin)
        self.db_session.add(cisco)
        self.db_session.commit()

    def test_meta(self):
        response, = self.simulate_request('/characters/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'Barry', 'team_id': 1}, 'meta': {'catchphrase': None}
        })

        response, = self.simulate_request('/characters/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Oliver', 'team_id': 2}, 'meta': {'catchphrase': 'You have failed this city'}
        })

        response, = self.simulate_request('/characters/3', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'name': 'Caitlin', 'team_id': 1}, 'meta': {'catchphrase': None}
        })

        response, = self.simulate_request('/characters/4', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 4, 'name': 'Cisco', 'team_id': 1}, 'meta': {'catchphrase': "OK, you don't get to pick the names"}
        })

        response, = self.simulate_request('/characters', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Barry', 'team_id': 1, 'meta': {'catchphrase': None}},
                {'id': 2, 'name': 'Oliver', 'team_id': 2, 'meta': {'catchphrase': 'You have failed this city'}},
                {'id': 3, 'name': 'Caitlin', 'team_id': 1, 'meta': {'catchphrase': None}},
                {'id': 4, 'name': 'Cisco', 'team_id': 1, 'meta': {'catchphrase': "OK, you don't get to pick the names"}},
            ]
        })

    def test_join_meta(self):
        response, = self.simulate_request('/extended-characters/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'Barry', 'team_id': 1}, 'meta': {'catchphrase': None, 'team_name': 'Team Flash'}
        })

        response, = self.simulate_request('/extended-characters/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Oliver', 'team_id': 2}, 'meta': {'catchphrase': 'You have failed this city', 'team_name': 'Team Arrow'}
        })

        response, = self.simulate_request('/extended-characters/3', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'name': 'Caitlin', 'team_id': 1}, 'meta': {'catchphrase': None, 'team_name': 'Team Flash'}
        })

        response, = self.simulate_request('/extended-characters/4', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 4, 'name': 'Cisco', 'team_id': 1}, 'meta': {'catchphrase': "OK, you don't get to pick the names", 'team_name': 'Team Flash'}
        })

        response, = self.simulate_request('/extended-characters', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Barry', 'team_id': 1, 'meta': {'catchphrase': None, 'team_name': 'Team Flash'}},
                {'id': 2, 'name': 'Oliver', 'team_id': 2, 'meta': {'catchphrase': 'You have failed this city', 'team_name': 'Team Arrow'}},
                {'id': 3, 'name': 'Caitlin', 'team_id': 1, 'meta': {'catchphrase': None, 'team_name': 'Team Flash'}},
                {'id': 4, 'name': 'Cisco', 'team_id': 1, 'meta': {'catchphrase': "OK, you don't get to pick the names", 'team_name': 'Team Flash'}},
            ]
        })

    def test_group_func_meta(self):
        response, = self.simulate_request('/teams/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'Team Flash'}, 'meta': {'team_size': 3},
        })

        response, = self.simulate_request('/teams/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Team Arrow'}, 'meta': {'team_size': 1},
        })

        response, = self.simulate_request('/teams', query_string='__sort=id', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Team Flash', 'meta': {'team_size': 3}},
                {'id': 2, 'name': 'Team Arrow', 'meta': {'team_size': 1}},
            ]
        })

    def test_dynamic_meta(self):
        response, = self.simulate_request('/dynamic-teams/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'Team Flash'}, 'meta': {'team_size': 3},
        })
        response, = self.simulate_request('/dynamic-teams-without-size/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'Team Flash'}, 'meta': {'state': 'busy'},
        })

        response, = self.simulate_request('/dynamic-teams/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Team Arrow'}, 'meta': {'team_size': 1},
        })
        response, = self.simulate_request('/dynamic-teams/2', query_string='__without_size=1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Team Arrow'},
        })
        response, = self.simulate_request('/dynamic-teams-without-size/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Team Arrow'}, 'meta': {'state': 'busy'},
        })

        response, = self.simulate_request('/dynamic-teams', query_string='__sort=id', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Team Flash', 'meta': {'team_size': 3}},
                {'id': 2, 'name': 'Team Arrow', 'meta': {'team_size': 1}},
            ]
        })
        response, = self.simulate_request('/dynamic-teams', query_string='__sort=id&__without_size=1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Team Flash'},
                {'id': 2, 'name': 'Team Arrow'},
            ]
        })
        response, = self.simulate_request('/dynamic-teams-without-size', query_string='__sort=id&__without_size=1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'Team Flash', 'meta': {'state': 'busy'}},
                {'id': 2, 'name': 'Team Arrow', 'meta': {'state': 'busy'}},
            ]
        })
