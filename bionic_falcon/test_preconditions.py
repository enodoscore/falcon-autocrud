from datetime import datetime
from .test_base import Base, BaseTestCase
from .test_fixtures import VersionedAccount

from falcon.errors import HTTPUnauthorized, HTTPForbidden
import json

from .resource import CollectionResource, SingleResource


class AccountCollectionResource(CollectionResource):
    model = VersionedAccount
    response_fields = ['id', 'name', 'owner']

    def get_filter(self, req, resp, query, *args, **kwargs):
        # Only allow getting accounts below id 5
        return query.filter(VersionedAccount.id < 5, VersionedAccount.deleted == None)

do_before_patch     = None
do_before_delete    = None

class AccountResource(SingleResource):
    model = VersionedAccount
    response_fields = ['id', 'name', 'owner']

    def get_filter(self, req, resp, query, *args, **kwargs):
        # Only allow getting accounts below id 5
        return query.filter(VersionedAccount.id < 5, VersionedAccount.deleted == None)

    def patch_precondition(self, req, resp, query, *args, **kwargs):
        # Only allow setting owner of non-owned account
        if 'owner' in req.context['doc'] and req.context['doc']['owner'] is not None:
            return query.filter(VersionedAccount.owner == None)
        else:
            return query

    def before_patch(req, resp, db_session, resource, *args, **kwargs):
        if do_before_patch is not None:
            do_before_patch(req, resp, db_session, resource, *args, **kwargs)

    def delete_precondition(self, req, resp, query, *args, **kwargs):
        # Only allow deletes of non-owned accounts
        return query.filter(VersionedAccount.owner == None)

    def before_delete(req, resp, db_session, resource, *args, **kwargs):
        if do_before_delete is not None:
            do_before_delete(req, resp, db_session, resource, *args, **kwargs)

    def mark_deleted(self, req, resp, resource, *args, **kwargs):
        resource.deleted = datetime.utcnow()


class PreconditionTest(BaseTestCase):
    def setUp(self):
        super(PreconditionTest, self).setUp()
        global do_before_patch, do_before_delete
        do_before_patch     = None
        do_before_delete    = None

    def tearDown(self):
        super(PreconditionTest, self).tearDown()
        global do_before_patch, do_before_delete
        do_before_patch     = None
        do_before_delete    = None

    def create_test_resources(self):
        self.app.add_route('/accounts', AccountCollectionResource(self.db_engine))
        self.app.add_route('/accounts/{id}', AccountResource(self.db_engine))

    def test_collection_get_filter(self):
        self.db_session.add(VersionedAccount(id=1, name="Foo", owner=None))
        self.db_session.add(VersionedAccount(id=2, name="Bar", owner=None))
        self.db_session.add(VersionedAccount(id=5, name="Baz", owner=None))
        self.db_session.commit()

        response, = self.simulate_request('/accounts', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': [{'id': 1, 'name': 'Foo', 'owner': None}, {'id': 2, 'name': 'Bar', 'owner': None}]})

        response, = self.simulate_request('/accounts', query_string='id=1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': [{'id': 1, 'name': 'Foo', 'owner': None}]})

        response, = self.simulate_request('/accounts', query_string='id=5', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': []})

        response, = self.simulate_request('/accounts', query_string='id__lt=10', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': [{'id': 1, 'name': 'Foo', 'owner': None}, {'id': 2, 'name': 'Bar', 'owner': None}]})

    def test_get_filter(self):
        self.db_session.add(VersionedAccount(id=1, name="Foo", owner=None))
        self.db_session.add(VersionedAccount(id=2, name="Bar", owner=None))
        self.db_session.add(VersionedAccount(id=5, name="Baz", owner=None))
        self.db_session.commit()

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': None}})

        response, = self.simulate_request('/accounts/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 2, 'name': 'Bar', 'owner': None}})

        response = self.simulate_request('/accounts/5', method='GET', headers={'Accept': 'application/json'})
        self.assertNotFound(response)

        response = self.simulate_request('/accounts/5', query_string='id=5', method='GET', headers={'Accept': 'application/json'})
        self.assertNotFound(response)

    def test_patch_precondition(self):
        self.db_session.add(VersionedAccount(id=1, name="Foo", owner=None))
        self.db_session.commit()

        #
        response, = self.simulate_request('/accounts/1', method='PATCH', body=json.dumps({'owner': 'Don Draper'}), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.assertOK(response)

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': 'Don Draper'}})

        #
        response, = self.simulate_request('/accounts/1', method='PATCH', body=json.dumps({'owner': 'Pete Campbell'}), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.assertConflict(response, 'Resource found but conditions violated')

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': 'Don Draper'}})

        #
        response, = self.simulate_request('/accounts/1', method='PATCH', body=json.dumps({'owner': 'Pete Campbell'}), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.assertConflict(response, 'Resource found but conditions violated')

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': 'Don Draper'}})

        #
        response, = self.simulate_request('/accounts/1', method='PATCH', body=json.dumps({'owner': None}), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.assertOK(response)

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': None}})

        #
        response, = self.simulate_request('/accounts/1', method='PATCH', body=json.dumps({'owner': 'Pete Campbell'}), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.assertOK(response)

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': 'Pete Campbell'}})

    def test_patch_precondition_with_race_condition(self):
        self.db_session.add(VersionedAccount(id=1, name="Foo", owner=None))
        self.db_session.commit()

        def set_owner_in_other_process(req, resp, db_session, resource, *args, **kwargs):
            account = self.db_session.query(VersionedAccount).get(1)
            account.owner = 'Pete Campbell'
            self.db_session.add(account)
            self.db_session.commit()
        global do_before_patch
        do_before_patch = set_owner_in_other_process

        response, = self.simulate_request('/accounts/1', method='PATCH', body=json.dumps({'owner': 'Don Draper'}), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        self.assertConflict(response, 'Resource found but conditions violated')

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': 'Pete Campbell'}})

    def test_delete_precondition(self):
        self.db_session.add(VersionedAccount(id=1, name="Foo", owner=None))
        self.db_session.add(VersionedAccount(id=2, name="Bar", owner="Don Draper"))
        self.db_session.commit()

        response, = self.simulate_request('/accounts/1', method='DELETE', headers={'Accept': 'application/json'})
        self.assertOK(response)

        response = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertNotFound(response)

        response, = self.simulate_request('/accounts/2', method='DELETE', headers={'Accept': 'application/json'})
        self.assertConflict(response, 'Resource found but conditions violated')

        response, = self.simulate_request('/accounts/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response)

    def test_delete_precondition_with_race_condition(self):
        self.db_session.add(VersionedAccount(id=1, name="Foo", owner=None))
        self.db_session.commit()

        def set_owner_in_other_process(req, resp, db_session, resource, *args, **kwargs):
            account = self.db_session.query(VersionedAccount).get(1)
            account.owner = 'Don Draper'
            self.db_session.add(account)
            self.db_session.commit()
        global do_before_delete
        do_before_delete = set_owner_in_other_process

        response, = self.simulate_request('/accounts/1', method='DELETE', headers={'Accept': 'application/json'})
        self.assertConflict(response, 'Resource found but conditions violated')

        response, = self.simulate_request('/accounts/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {'data': {'id': 1, 'name': 'Foo', 'owner': 'Don Draper'}})
