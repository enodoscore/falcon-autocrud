import json
from sqlalchemy import Column, Integer, String

from .test_base import Base, BaseTestCase
from .test_fixtures import Employee

from .resource import CollectionResource, SingleResource


class EmployeeCollectionResource(CollectionResource):
    model = Employee

class EmployeeResource(SingleResource):
    model = Employee

class LimitedEmployeeCollectionResource(CollectionResource):
    model = Employee

    response_fields = ['id', 'name']

class LimitedEmployeeResource(SingleResource):
    model = Employee

    response_fields = ['id', 'name']

to_return = []

class ProgrammaticallyLimitedEmployeeCollectionResource(CollectionResource):
    model = Employee

    def response_fields(self, req, resp, resource, *args, **kwargs):
        return req.get_header('X-Fields').split(',')

class ProgrammaticallyLimitedEmployeeResource(SingleResource):
    model = Employee

    def response_fields(self, req, resp, resource, *args, **kwargs):
        return req.get_header('X-Fields').split(',')


class SortTest(BaseTestCase):
    def create_test_resources(self):
        self.app.add_route('/employees', EmployeeCollectionResource(self.db_engine))
        self.app.add_route('/employees/{id}', EmployeeResource(self.db_engine))
        self.app.add_route('/limited-employees', LimitedEmployeeCollectionResource(self.db_engine))
        self.app.add_route('/limited-employees/{id}', LimitedEmployeeResource(self.db_engine))
        self.app.add_route('/programmatically-limited-employees', ProgrammaticallyLimitedEmployeeCollectionResource(self.db_engine))
        self.app.add_route('/programmatically-limited-employees/{id}', ProgrammaticallyLimitedEmployeeResource(self.db_engine))

    def create_common_fixtures(self):
        response, = self.simulate_request('/employees', method='POST', body=json.dumps({'id': 1, 'name': 'John'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        response, = self.simulate_request('/employees', method='POST', body=json.dumps({'id': 2, 'name': 'Barry'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})

    def test_full_fields(self):
        response, = self.simulate_request('/employees', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'John', 'joined': None, 'left': None, 'company_id': None, 'pay_rate': None, 'start_time': None, 'lunch_start': None, 'end_time': None, 'caps_name': None},
                {'id': 2, 'name': 'Barry', 'joined': None, 'left': None, 'company_id': None, 'pay_rate': None, 'start_time': None, 'lunch_start': None, 'end_time': None, 'caps_name': None},
            ]
        })
        response, = self.simulate_request('/employees/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'John', 'joined': None, 'left': None, 'company_id': None, 'pay_rate': None, 'start_time': None, 'lunch_start': None, 'end_time': None, 'caps_name': None},
        })
        response, = self.simulate_request('/employees/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Barry', 'joined': None, 'left': None, 'company_id': None, 'pay_rate': None, 'start_time': None, 'lunch_start': None, 'end_time': None, 'caps_name': None},
        })

    def test_limited_fields(self):
        response, = self.simulate_request('/limited-employees', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'John'},
                {'id': 2, 'name': 'Barry'},
            ]
        })
        response, = self.simulate_request('/limited-employees/1', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'John'},
        })
        response, = self.simulate_request('/limited-employees/2', method='GET', headers={'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Barry'},
        })

        response, = self.simulate_request('/limited-employees', method='POST', body=json.dumps({'id': 3, 'name': 'Cisco'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertCreated(response, {
            'data': {'id': 3, 'name': 'Cisco'},
        })

        response, = self.simulate_request('/limited-employees/3', method='PUT', body=json.dumps({'id': 4, 'name': 'Caitlin'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 4, 'name': 'Caitlin'},
        })

        response, = self.simulate_request('/limited-employees/4', method='PATCH', body=json.dumps({'name': 'Iris'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 4, 'name': 'Iris'},
        })

    def test_programmatically_limited_fields(self):
        response, = self.simulate_request('/programmatically-limited-employees', method='GET', headers={'X-Fields': 'id,name', 'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'name': 'John'},
                {'id': 2, 'name': 'Barry'},
            ]
        })
        response, = self.simulate_request('/programmatically-limited-employees', method='GET', headers={'X-Fields': 'id,caps_name', 'Accept': 'application/json'})
        self.assertOK(response, {
            'data': [
                {'id': 1, 'caps_name': None},
                {'id': 2, 'caps_name': None},
            ]
        })

        response, = self.simulate_request('/programmatically-limited-employees/1', method='GET', headers={'X-Fields': 'id,name', 'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'name': 'John'},
        })
        response, = self.simulate_request('/programmatically-limited-employees/1', method='GET', headers={'X-Fields': 'id,caps_name', 'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 1, 'caps_name': None},
        })

        response, = self.simulate_request('/programmatically-limited-employees/2', method='GET', headers={'X-Fields': 'id,name', 'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'name': 'Barry'},
        })
        response, = self.simulate_request('/programmatically-limited-employees/2', method='GET', headers={'X-Fields': 'id,caps_name', 'Accept': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 2, 'caps_name': None},
        })

        response, = self.simulate_request('/programmatically-limited-employees', method='POST', body=json.dumps({'id': 3, 'name': 'Cisco'}), headers={'X-Fields': 'id,name', 'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertCreated(response, {
            'data': {'id': 3, 'name': 'Cisco'},
        })
        response, = self.simulate_request('/programmatically-limited-employees', method='POST', body=json.dumps({'id': 4, 'name': 'Cisco 2'}), headers={'X-Fields': 'id,caps_name', 'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertCreated(response, {
            'data': {'id': 4, 'caps_name': None},
        })

        response, = self.simulate_request('/programmatically-limited-employees/3', method='PUT', body=json.dumps({'id': 3, 'name': 'Caitlin'}), headers={'X-Fields': 'id,name', 'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'name': 'Caitlin'},
        })
        response, = self.simulate_request('/programmatically-limited-employees/3', method='PUT', body=json.dumps({'id': 3, 'name': 'Caitlin 2'}), headers={'X-Fields': 'id,caps_name', 'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'caps_name': None},
        })

        response, = self.simulate_request('/programmatically-limited-employees/3', method='PATCH', body=json.dumps({'name': 'Iris'}), headers={'X-Fields': 'id,name', 'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'name': 'Iris'},
        })
        response, = self.simulate_request('/programmatically-limited-employees/3', method='PATCH', body=json.dumps({'name': 'Iris 2'}), headers={'X-Fields': 'id,caps_name', 'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertOK(response, {
            'data': {'id': 3, 'caps_name': None},
        })
