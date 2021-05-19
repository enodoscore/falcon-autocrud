from .middleware import Middleware
from .schema import request_schema, response_schema, SchemaDecoratorError

import falcon, falcon.testing
import json
import logging
import unittest


class CollectingHandler(logging.Handler):
    def __init__(self):
        super(CollectingHandler, self).__init__()
        self.logs = []
    def emit(self, record):
        self.logs.append(record)

post_schema = {
    'type': 'object',
    'properties': {
        'email':    {'type': 'string'},
        'password': {'type': 'string'},
    },
    'required': ['email', 'password'],
}
post_response_schema = {
    'type': 'object',
    'properties': {
    },
}

class TestDefaultNoKeepBodyResource(object):
    @request_schema(post_schema)
    @response_schema(post_response_schema)
    def on_post(self, req, resp):
        self.request_body = req.context.get('request_body')
        resp.status = falcon.HTTP_201
        req.context['result'] = {}

    @request_schema(post_schema)
    @response_schema(post_response_schema)
    def on_patch(self, req, resp):
        self.request_body = req.context.get('request_body')
        resp.status = falcon.HTTP_201
        req.context['result'] = {}

class TestKeepBodyResource(object):
    keep_request_body = ['POST']

    @request_schema(post_schema)
    @response_schema(post_response_schema)
    def on_post(self, req, resp):
        self.request_body = req.context.get('request_body')
        resp.status = falcon.HTTP_201
        req.context['result'] = {}

    @request_schema(post_schema)
    @response_schema(post_response_schema)
    def on_patch(self, req, resp):
        self.request_body = req.context.get('request_body')
        resp.status = falcon.HTTP_201
        req.context['result'] = {}

class MiddlewareTest(unittest.TestCase):
    def setUp(self):
        super(MiddlewareTest, self).setUp()

        self.logger = logging.getLogger('TestLogger')
        self.handler = CollectingHandler()
        self.logger.handlers = []
        self.logger.addHandler(self.handler)

        self.app = falcon.API(
            middleware=[Middleware(self.logger)],
        )

        self.default_do_not_keep_body_resource = TestDefaultNoKeepBodyResource()
        self.keep_body_resource = TestKeepBodyResource()

        self.app.add_route('/test_default_do_not_keep_body', self.default_do_not_keep_body_resource)
        self.app.add_route('/test_keep_body', self.keep_body_resource)

        self.srmock = falcon.testing.StartResponseMock()

    def simulate_request(self, path, *args, **kwargs):
        env = falcon.testing.create_environ(path=path, **kwargs)
        return self.app(env, self.srmock)

    def test_do_not_keep_body_by_default(self):
        response, = self.simulate_request('/test_default_do_not_keep_body', method='POST', body=json.dumps({'email': 'foo@example.com', 'password': 'hunter2'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertIsNone(self.default_do_not_keep_body_resource.request_body)
        response, = self.simulate_request('/test_default_do_not_keep_body', method='PATCH', body=json.dumps({'email': 'foo@example.com', 'password': 'hunter2'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertIsNone(self.default_do_not_keep_body_resource.request_body)

    def test_do_not_keep_body(self):
        response, = self.simulate_request('/test_keep_body', method='PATCH', body=json.dumps({'email': 'foo@example.com', 'password': 'hunter2'}), headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertIsNone(self.keep_body_resource.request_body)

    def test_keep_body(self):
        body = json.dumps({'email': 'foo@example.com', 'password': 'hunter2'})
        response, = self.simulate_request('/test_keep_body', method='POST', body=body, headers={'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.assertEqual(self.keep_body_resource.request_body, body.encode('utf-8'))
