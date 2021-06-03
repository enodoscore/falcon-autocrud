from datetime import date, datetime, time
from time import mktime
from decimal import Decimal
import falcon
import falcon.errors
import itertools
import sqlalchemy.exc
import sqlalchemy.orm.exc
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.session import make_transient
import sqlalchemy.sql.sqltypes
import uuid
import logging

from .db_session import session_scope

def identify(req, resp, resource, params):
    identifiers = getattr(resource, '__identifiers__', {})
    if req.method in identifiers:
        Identifier = identifiers[req.method]
        Identifier().identify(req, resp, resource, params)

def authorize(req, resp, resource, params):
    authorizers = getattr(resource, '__authorizers__', {})
    if req.method in authorizers:
        Authorizer = authorizers[req.method]
        Authorizer().authorize(req, resp, resource, params)


class UnsupportedGeometryType(Exception):
    pass

try:
    import geoalchemy2.shape
    from geoalchemy2.elements import WKBElement
    from geoalchemy2.types import Geometry
    from shapely.geometry import Point, LineString, Polygon
    support_geo = True
except ImportError:
    support_geo = False


def _get_response_fields(self, req, resp, resource, *args, **kwargs):
    response_fields = getattr(self, 'response_fields', None)
    if callable(response_fields):
        return response_fields(req, resp, resource, *args, **kwargs)
    else:
        return response_fields

class BaseResource(object):
    def _is_foreign_key_violation(self, error):
        args = error.orig.args
        return self.db_engine.url.get_backend_name() == 'postgresql' and \
            args[0] == 'ERROR' and (
            args[1] == '23503' or                       # Postgres 9.5
            (args[1] == 'ERROR' and args[2] == '23503') # Postgres 9.6
        )

    def _is_unique_violation(self, error):
        args = error.orig.args
        return self.db_engine.url.get_backend_name() == 'postgresql' and \
            args[0] == 'ERROR' and (
            args[1] == '23505' or                       # Postgres 9.5
            (args[1] == 'ERROR' and args[2] == '23505') # Postgres 9.6
        )

    def __init__(self, db_engine, logger=None, sessionmaker_=sessionmaker, sessionmaker_kwargs={}):
        self.db_engine = db_engine
        self.sessionmaker = sessionmaker_
        self.sessionmaker_kwargs = sessionmaker_kwargs
        if logger is None:
            logger = logging.getLogger('bionic')
        self.logger = logger

    def param_string_to_list(self, value: str):
        if not value.startswith('[') or not value.endswith(']'):
            raise falcon.errors.HTTPBadRequest('Invalid attribute', f'Query __in filter value \'{value}\' is an invalid list string. Lists should be formatted as [a,b,c].')
        value = value[1:-1]
        if value == '':
            raise falcon.errors.HTTPBadRequest('Invalid attribute', f'Query __in filter provided an empty list string. Please omit unused parameters.')
        return value.split(',')

    def filter_by_params(self, resources, params):
        for filter_key, value in params.items():
            if filter_key.startswith('__'):
                # Not a filtering parameter
                continue
            filter_parts = filter_key.split('__')
            key = filter_parts[0]
            if len(filter_parts) == 1:
                comparison = '='
            elif len(filter_parts) == 2:
                comparison = filter_parts[1]
            else:
                raise falcon.errors.HTTPBadRequest('Invalid attribute', 'An attribute provided for filtering is invalid')

            attr = getattr(self.model, key, None)
            if attr is None or not isinstance(inspect(self.model).attrs[key], ColumnProperty):
                self.logger.warn('An attribute ({0}) provided for filtering is invalid'.format(key))
                raise falcon.errors.HTTPBadRequest('Invalid attribute', 'An attribute provided for filtering is invalid')
            if comparison == '=':
                resources = resources.filter(attr == value)
            elif comparison == 'null':
                if value != '0':
                    resources = resources.filter(attr.is_(None))
                else:
                    resources = resources.filter(attr.isnot(None))
            elif comparison == 'startswith':
                resources = resources.filter(attr.like('{0}%'.format(value)))
            elif comparison == 'istartswith':
                resources = resources.filter(attr.ilike('{0}%'.format(value)))
            elif comparison == 'endswith':
                resources = resources.filter(attr.like('%{0}'.format(value)))
            elif comparison == 'iendswith':
                resources = resources.filter(attr.ilike('%{0}'.format(value)))
            elif comparison == 'contains':
                resources = resources.filter(attr.like('%{0}%'.format(value)))
            elif comparison == 'icontains':
                resources = resources.filter(attr.ilike('%{0}%'.format(value)))
            elif comparison == 'lt':
                resources = resources.filter(attr < value)
            elif comparison == 'lte':
                resources = resources.filter(attr <= value)
            elif comparison == 'gt':
                resources = resources.filter(attr > value)
            elif comparison == 'gte':
                resources = resources.filter(attr >= value)
            elif comparison == 'in':
                resources = resources.filter(attr.in_(self.param_string_to_list(value)))
            else:
                raise falcon.errors.HTTPBadRequest('Invalid attribute', 'An attribute provided for filtering is invalid')
        return resources

    def serialize(self, resource, response_fields=None, geometry_axes=None):
        attrs           = inspect(resource.__class__).attrs

        def _serialize_value(name, value):
            if isinstance(value, list):
                return [_serialize_value('', val) for val in value]
            if isinstance(value, uuid.UUID):
                return value.hex
            if isinstance(value, datetime):
                if name in getattr(self, 'naive_datetimes', []): # List of naive datetime columns:
                    return value.strftime('%Y-%m-%dT%H:%M:%S')
                elif name in getattr(self, 'datetime_in_ms', []): # List of datetime columns to keep as ms since Unix epoch:
                    try:
                        return int(mktime(value.timetuple()))
                    except:
                        return None
                else:
                    return value.strftime('%Y-%m-%dT%H:%M:%SZ')
            elif isinstance(value, date):
                return value.strftime('%Y-%m-%d')
            elif isinstance(value, time):
                return value.isoformat()
            elif isinstance(value, Decimal):
                return float(value)
            elif support_geo and isinstance(value, WKBElement):
                value = geoalchemy2.shape.to_shape(value)
                if isinstance(value, Point):
                    axes = (geometry_axes or {}).get(name, ['x', 'y', 'z'])[0:attrs[name].columns[0].type.dimension]
                    return dict(itertools.zip_longest(axes, value.coords[0]))
                elif isinstance(value, LineString):
                    axes = (geometry_axes or {}).get(name, ['x', 'y', 'z'])[0:attrs[name].columns[0].type.dimension]
                    return [
                        dict(itertools.zip_longest(axes, point))
                        for point in list(value.coords)
                    ]
                elif isinstance(value, Polygon):
                    axes = (geometry_axes or {}).get(name, ['x', 'y', 'z'])[0:attrs[name].columns[0].type.dimension]
                    return [
                        dict(itertools.zip_longest(axes, point))
                        for point in list(value.boundary.coords)
                    ]
                else:
                    raise UnsupportedGeometryType('Unsupported geometry type {0}'.format(value.geometryType()))
            else:
                return value
        if response_fields is None:
            response_fields = attrs.keys()
        return {
            attr: _serialize_value(attr, getattr(resource, attr)) for attr in response_fields if isinstance(attrs[attr], ColumnProperty)
        }

    def _inbound_attribute(self, name):
        attr_map = getattr(
            self,
            'inbound_attr_map',
            getattr(self, 'attr_map', {})
        )
        return attr_map.get(name, name)

    def _lookup_attribute(self, name):
        attr_map = getattr(
            self,
            'lookup_attr_map',
            getattr(self, 'attr_map', {})
        )
        return attr_map.get(name, name)
    
    def parse_body_dict(self, model, allow_recursion, body_data):
        attributes          = {}
        linked_attributes   = {}
        mapper              = inspect(model)

        for key, value in body_data.items():
            if isinstance(getattr(model, key, None), property):
                # Value is set using a function, so we cannot tell what type it will be
                attributes[key] = value
                continue
            try:
                column = mapper.columns[key]
            except KeyError:
                if not allow_recursion:
                    # Assume programmer has done their job of filtering out invalid
                    # columns, and that they are going to use this field for some
                    # custom purpose
                    continue
                try:
                    relationship = mapper.relationships[key]
                    if relationship.uselist:
                        linked_attributes[key] = [ self.parse_body_dict(relationship.mapper.entity, False, entity)[0] for entity in value ]
                    else:
                        linked_attributes[key] = self.parse_body_dict(relationship.mapper.entity, False, value)[0]
                    continue
                except KeyError:
                    # Assume programmer has done their job of filtering out invalid
                    # columns, and that they are going to use this field for some
                    # custom purpose
                    continue
            if isinstance(column.type, sqlalchemy.sql.sqltypes.DateTime):
                if value is None:
                    attributes[key] = None
                elif key in getattr(self, 'datetime_in_ms', []): # List of datetime columns to keep as ms since Unix epoch
                    attributes[key] = datetime.fromtimestamp(value)
                elif key in getattr(self, 'naive_datetimes', []): # List of naive datetime columns
                    attributes[key] = datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
                else:
                    attributes[key] = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
            elif isinstance(column.type, sqlalchemy.sql.sqltypes.Date):
                attributes[key] = datetime.strptime(value, '%Y-%m-%d').date() if value is not None else None
            elif isinstance(column.type, sqlalchemy.sql.sqltypes.Time):
                if value is not None:
                    hour, minute, second = value.split(':')
                    attributes[key] = time(int(hour), int(minute), int(second))
                else:
                    attributes[key] = None
            elif support_geo and isinstance(column.type, Geometry) and column.type.geometry_type in ['POINT', 'POINTZ']:
                axes    = getattr(self, 'geometry_axes', {}).get(key, ['x', 'y', 'z'] if column.type.geometry_type == 'POINTZ' else ['x', 'y'])
                point   = Point(*list(value.get(axes[index], 0) for index in range(0, len(axes))))
                # geoalchemy2.shape.from_shape uses buffer() which causes INSERT to fail
                attributes[key] = WKBElement(point.wkb, srid=4326)
            elif support_geo and isinstance(column.type, Geometry) and column.type.geometry_type in ['LINESTRING', 'LINESTRINGZ']:
                axes    = getattr(self, 'geometry_axes', {}).get(key, ['x', 'y', 'z'] if column.type.geometry_type == 'LINESTRINGZ' else ['x', 'y'])
                line    = LineString([point.get(axes[index], 0) for index in range(0, len(axes))] for point in value)
                # geoalchemy2.shape.from_shape uses buffer() which causes INSERT to fail
                attributes[key] = WKBElement(line.wkb, srid=4326)
            elif support_geo and isinstance(column.type, Geometry) and column.type.geometry_type in ['POLYGON', 'POLYGONZ']:
                axes    = getattr(self, 'geometry_axes', {}).get(key, ['x', 'y', 'z'] if column.type.geometry_type == 'POLYGONZ' else ['x', 'y'])
                polygon = Polygon([point.get(axes[index], 0) for index in range(0, len(axes))] for point in value)
                # geoalchemy2.shape.from_shape uses buffer() which causes INSERT to fail
                attributes[key] = WKBElement(polygon.wkb, srid=4326)
            else:
                attributes[key] = value

        return (attributes, linked_attributes)
    
    def parse_path_dict(self, model, path_data):
        path_attributes      = {}

        for key, value in path_data.items():
            key = self._inbound_attribute(key)
            if key is None:
                continue
            elif callable(key):
                continue # Ignore, as it is only defined for lookup purposes
            elif getattr(model, key, None) is None or not isinstance(inspect(model).attrs[key], ColumnProperty):
                self.logger.error("Programming error: {0}.attr_map['{1}'] does not exist or is not a column".format(model, key))
                raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')
            path_attributes[key] = value

        return path_attributes

    def deserialize(self, model, path_data, body_data, allow_recursion=False):
        to_parse = [body_data] if type(body_data) is not list else body_data

        deserialized = [self.parse_body_dict(model, allow_recursion, body_dict) for body_dict in to_parse]
        path_attributes = self.parse_path_dict(model, path_data)
        for attributes, _ in deserialized:
            for key, val in path_attributes.items():
                attributes[key] = val

        return list(zip(*deserialized))

    def apply_arg_filter(self, req, resp, resources, kwargs):
        for key, value in kwargs.items():
            key = self._lookup_attribute(key)
            if key is None:
                continue
            elif callable(key):
                resources = key(req, resp, resources, **kwargs)
            else:
                attr = getattr(self.model, key, None)
                if attr is None or not isinstance(inspect(self.model).attrs[key], ColumnProperty):
                    self.logger.error("Programming error: {0}.attr_map['{1}'] does not exist or is not a column".format(self.model, key))
                    raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')
                resources = resources.filter(attr == value)
        return resources

    def apply_default_attributes(self, defaults_type, req, resp, attributes):
        defaults = getattr(self, defaults_type, {})
        for key, setter in defaults.items():
            if key not in attributes:
                attributes[key] = setter(req, resp, attributes)

class CollectionResource(BaseResource):
    """
    Provides CRUD facilities for a resource collection.
    """

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query

    @falcon.before(identify)
    @falcon.before(authorize)
    def on_get(self, req, resp, *args, **kwargs):
        """
        Return a collection of items.
        """
        if 'GET' not in getattr(self, 'methods', ['GET', 'POST', 'PATCH']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'POST', 'PATCH']))

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            column_filters = kwargs
            before_get = getattr(self, 'before_get', None)
            if before_get is not None:
                self.before_get(req, resp, db_session, column_filters, *args)
            kwargs = column_filters

            extra_select    = getattr(self, 'extra_select', [])
            resources       = self.apply_arg_filter(req, resp, db_session.query(self.model, *extra_select), kwargs)

            resources = self.filter_by_params(
                self.get_filter(
                    req, resp,
                    resources,
                    *args, **kwargs
                ),
                req.params
            )

            sort                = getattr(self, 'default_sort', None)
            using_default_sort  = True
            if '__sort' in req.params:
                using_default_sort = False
                sort = req.get_param_as_list('__sort')
            if sort is not None:
                order_fields = []
                for field_name in sort:
                    reverse = False
                    if field_name[0] == '-':
                        field_name = field_name[1:]
                        reverse = True
                    attr = getattr(self.model, field_name, None)
                    if attr is None or not isinstance(inspect(self.model).attrs[field_name], ColumnProperty):
                        if using_default_sort:
                            self.logger.error("Programming error: Sort field {0}.{1} does not exist or is not a column".format(self.model, field_name))
                            raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')
                        else:
                            raise falcon.errors.HTTPBadRequest('Invalid attribute', 'An attribute provided for sorting is invalid')
                    if reverse:
                        order_fields.append(attr.desc())
                    else:
                        order_fields.append(attr)
                resources = resources.order_by(*order_fields)
            count = None
            if req.get_param_as_int('__offset'):
                count     = resources.count()
                resources = resources.offset(req.get_param_as_int('__offset'))
            if req.get_param_as_int('__limit'):
                if count is None:
                    count     = resources.count()
                resources = resources.limit(req.get_param_as_int('__limit'))

            resource_meta = getattr(self, 'resource_meta', {})

            def add_meta(resource, attributes):
                output = attributes.copy()
                if callable(resource_meta):
                    if len(extra_select) > 0:
                        meta_dict = resource_meta(req, resp, *list(itertools.chain(resource, args)), **kwargs)
                    else:
                        meta_dict = resource_meta(req, resp, resource, *args, **kwargs)
                    if meta_dict is not None:
                        output['meta'] = meta_dict
                elif len(resource_meta.keys()) > 0:
                    if len(extra_select) > 0:
                        output['meta'] = {key: value(*resource) for key, value in resource_meta.items()}
                    else:
                        output['meta'] = {key: value(resource) for key, value in resource_meta.items()}
                return output

            resp.status = falcon.HTTP_OK
            result = {
                'data': [
                    add_meta(
                        resource,
                        self.serialize(
                            resource[0] if len(extra_select) > 0 else resource,
                            _get_response_fields(self, req, resp, resource, *args, **kwargs),
                            getattr(self, 'geometry_axes', {})
                        )
                    )
                    for resource in resources
                ],
            }
            if '__offset' in req.params or '__limit' in req.params:
                result['meta'] = {'total': count}
                if '__offset' in req.params:
                    result['meta']['offset'] = req.get_param_as_int('__offset')
                if '__limit' in req.params:
                    result['meta']['limit'] = req.get_param_as_int('__limit')

            req.context['result'] = result

            after_get = getattr(self, 'after_get', None)
            if after_get is not None:
                after_get(req, resp, resources, *args, **kwargs)

    @falcon.before(identify)
    @falcon.before(authorize)
    def on_post(self, req, resp, *args, **kwargs):
        """
        Add an item to the collection.
        """
        if 'POST' not in getattr(self, 'methods', ['GET', 'POST', 'PATCH']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'POST', 'PATCH']))

        attributes, linked_attributes = self.deserialize(self.model, kwargs, req.context['doc'] if 'doc' in req.context else None, getattr(self, 'allow_subresources', False))

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            single_entity = len(attributes) == 1

            for attribute_dict in attributes:
                self.apply_default_attributes('post_defaults', req, resp, attribute_dict)

            resources = [self.model(**attribute_dict) for attribute_dict in attributes]

            before_post = getattr(self, 'before_post', None)
            if before_post is not None:
                self.before_post(req, resp, db_session, resources[0] if single_entity else resources, *args, **kwargs)

            for resource in resources:
                db_session.add(resource)

            mapper = inspect(self.model)
            for resource, linked in zip(resources, linked_attributes):
                for key, value in linked.items():
                    relationship = mapper.relationships[key]
                    resource_class = relationship.mapper.entity
                    if relationship.uselist:
                        setattr(resource, key, [ resource_class(**attributes) for attributes in value ])
                    else:
                        subresource = resource_class(**value)
                        setattr(resource, key, subresource)

            try:
                db_session.commit()
            except sqlalchemy.exc.IntegrityError as err:
                # Cases such as unallowed NULL value should have been checked
                # before we got here (e.g. validate against schema
                # using the middleware) - therefore assume this is a UNIQUE
                # constraint violation
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
            except sqlalchemy.exc.ProgrammingError as err:
                db_session.rollback()
                if self._is_unique_violation(err):
                    raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
                else:
                    raise
            except:
                db_session.rollback()
                raise

            resp.status = falcon.HTTP_CREATED
            response_fields = _get_response_fields(self, req, resp, resources[0], *args, **kwargs)
            geometry_axes = getattr(self, 'geometry_axes', {})
            processed_data = [ self.serialize(resource, response_fields, geometry_axes) for resource in resources ]

            req.context['result'] = {
                'data': processed_data[0] if single_entity else processed_data
            }

            after_post = getattr(self, 'after_post', None)
            if after_post is not None:
                after_post(req, resp, resources[0] if single_entity else resources)

    @falcon.before(identify)
    @falcon.before(authorize)
    def on_patch(self, req, resp, *args, **kwargs):
        """
        Update a collection.

        For now, it only supports adding entities to the collection, like this:

        {
            'patches': [
                {'op': 'add', 'path': '/', 'value': {'name': 'Jim', 'age', 25}},
                {'op': 'add', 'path': '/', 'value': {'name': 'Bob', 'age', 28}}
            ]
        }

        """
        if 'PATCH' not in getattr(self, 'methods', ['GET', 'POST', 'PATCH']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'POST', 'PATCH']))

        patch_paths = getattr(self, 'patch_paths', {})
        if len(patch_paths) == 0:
            patch_paths['/'] = self.model
        patch_lookups = {
            path: {
                'model':    model,
                'mapper':   inspect(model),
            } for path, model in patch_paths.items()
        }
        patches = req.context['doc']['patches']

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            for index, patch in enumerate(patches):
                # Only support adding entities in a collection patch, for now
                if 'op' not in patch or patch['op'] not in ['add']:
                    raise falcon.errors.HTTPBadRequest('Invalid patch', 'Patch {0} is not valid'.format(index))
                if patch['op'] == 'add':
                    if 'path' not in patch or patch['path'] not in patch_paths:
                        raise falcon.errors.HTTPBadRequest('Invalid patch', 'Patch {0} is not valid for op {1}'.format(index, patch['op']))

                    model   = patch_lookups[patch['path']]['model']
                    mapper  = patch_lookups[patch['path']]['mapper']

                    try:
                        patch_value = patch['value']
                    except KeyError:
                        raise falcon.errors.HTTPBadRequest('Invalid patch', 'Patch {0} is not valid for op {1}'.format(index, patch['op']))
                    args = {}
                    for key, value in kwargs.items():
                        key = self._inbound_attribute(key)
                        if getattr(model, key, None) is None or not isinstance(inspect(model).attrs[key], ColumnProperty):
                            self.logger.error("Programming error: {0}.attr_map['{1}'] does not exist or is not a column".format(model, key))
                            raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')
                        args[key] = value
                    for key, value in patch_value.items():
                        if isinstance(mapper.columns[key].type, sqlalchemy.sql.sqltypes.DateTime):
                            args[key] = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
                        else:
                            args[key] = value
                    resource = model(**args)
                    db_session.add(resource)

            try:
                db_session.commit()
            except sqlalchemy.exc.IntegrityError as err:
                # Cases such as unallowed NULL value should have been checked
                # before we got here (e.g. validate against schema
                # using the middleware) - therefore assume this is a UNIQUE
                # constraint violation
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
            except sqlalchemy.exc.ProgrammingError as err:
                db_session.rollback()
                if self._is_unique_violation(err):
                    raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
                else:
                    raise
            except:
                db_session.rollback()
                raise

        resp.status = falcon.HTTP_OK
        req.context['result'] = {}

        after_patch = getattr(self, 'after_patch', None)
        if after_patch is not None:
            after_patch(req, resp, *args, **kwargs)

class SingleResource(BaseResource):
    """
    Provides CRUD facilities for a single resource.
    """

    def get_filter(self, req, resp, query, *args, **kwargs):
        return query

    @falcon.before(identify)
    @falcon.before(authorize)
    def on_get(self, req, resp, *args, **kwargs):
        """
        Return a single item.
        """
        if 'GET' not in getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']))

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            column_filters = kwargs
            before_get = getattr(self, 'before_get', None)
            if before_get is not None:
                self.before_get(req, resp, db_session, column_filters, *args)
            kwargs = column_filters

            extra_select    = getattr(self, 'extra_select', [])
            resources = self.apply_arg_filter(req, resp, db_session.query(self.model, *extra_select), kwargs)

            resources = self.get_filter(req, resp, resources, *args, **kwargs)

            try:
                resource = resources.one()
            except sqlalchemy.orm.exc.NoResultFound:
                raise falcon.errors.HTTPNotFound()
            except sqlalchemy.orm.exc.MultipleResultsFound:
                self.logger.error('Programming error: multiple results found for get of model {0}'.format(self.model))
                raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')

            resp.status = falcon.HTTP_OK
            result = {
                'data': self.serialize(
                    resource[0] if len(extra_select) > 0 else resource,
                    _get_response_fields(self, req, resp, resource, *args, **kwargs),
                    getattr(self, 'geometry_axes', {})
                ),
            }
            if '__included' in req.params:
                allowed_included = getattr(self, 'allowed_included', {})
                result['included'] = []
                for included in req.get_param_as_list('__included'):
                    if included not in allowed_included:
                        raise falcon.errors.HTTPBadRequest('Invalid parameter', 'The "__included" parameter includes invalid entities')
                    included_resources  = allowed_included[included]['link'](resource)
                    response_fields     = allowed_included[included].get('response_fields')
                    geometry_axes       = allowed_included[included].get('geometry_axes')

                    for included_resource in included_resources:
                        primary_key, = [
                            attr
                            for attr in inspect(included_resource.__class__).attrs.values()
                            if isinstance(attr, ColumnProperty) and attr.columns[0].primary_key
                        ]
                        result['included'].append({
                            'id':           getattr(resource, primary_key.key),
                            'type':         included,
                            'attributes':   self.serialize(
                                included_resource,
                                (
                                    response_fields(self, req, resp, included_resource, *args, **kwargs)
                                    if callable(response_fields)
                                    else
                                    response_fields
                                ),
                                geometry_axes
                            ),
                        })

            resource_meta = getattr(self, 'meta', {})
            if callable(resource_meta):
                if len(extra_select) > 0:
                    meta_dict = resource_meta(req, resp, *list(itertools.chain(resource, args)), **kwargs)
                else:
                    meta_dict = resource_meta(req, resp, resource, *args, **kwargs)
                if meta_dict is not None:
                    if 'meta' not in result:
                        result['meta'] = {}
                    result['meta'].update(meta_dict)
            else:
                meta_dict = resource_meta

                if len(meta_dict.keys()) > 0:
                    if 'meta' not in result:
                        result['meta'] = {}
                    for key, value in meta_dict.items():
                        if len(extra_select) > 0:
                            result['meta'][key] = value(*resource)
                        else:
                            result['meta'][key] = value(resource)

            req.context['result'] = result

            after_get = getattr(self, 'after_get', None)
            if after_get is not None:
                after_get(req, resp, resource, *args, **kwargs)

    def delete_precondition(self, req, resp, query, *args, **kwargs):
        return query

    @falcon.before(identify)
    @falcon.before(authorize)
    def on_delete(self, req, resp, *args, **kwargs):
        """
        Delete a single item.
        """
        if 'DELETE' not in getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']))

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            resources = self.apply_arg_filter(req, resp, db_session.query(self.model), kwargs)

            try:
                resource = resources.one()
            except sqlalchemy.orm.exc.NoResultFound:
                raise falcon.errors.HTTPNotFound()
            except sqlalchemy.orm.exc.MultipleResultsFound:
                self.logger.error('Programming error: multiple results found for patch of model {0}'.format(self.model))
                raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')

            resources = self.delete_precondition(
                req, resp,
                self.filter_by_params(resources, req.params),
                *args, **kwargs
            )

            try:
                resource = resources.one()
            except sqlalchemy.orm.exc.NoResultFound:
                raise falcon.errors.HTTPConflict('Conflict', 'Resource found but conditions violated')
            except sqlalchemy.orm.exc.MultipleResultsFound:
                self.logger.error('Programming error: multiple results found for delete of model {0}'.format(self.model))
                raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')

            before_delete = getattr(self, 'before_delete', None)
            if before_delete is not None:
                self.before_delete(req, resp, db_session, resource, *args, **kwargs)

            try:
                mark_deleted = getattr(self, 'mark_deleted', None)
                if mark_deleted is not None:
                    mark_deleted(req, resp, resource, *args, **kwargs)
                    db_session.add(resource)
                else:
                    make_transient(resource)
                    resources.delete()
                db_session.commit()
            except sqlalchemy.exc.IntegrityError as err:
                # As far we I know, this should only be caused by foreign key constraint being violated
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Other content links to this')
            except sqlalchemy.orm.exc.StaleDataError as err:
                # Version field in the model was not as expected
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Resource found but conditions violated')
            except sqlalchemy.exc.ProgrammingError as err:
                db_session.rollback()
                if self._is_foreign_key_violation(err):
                    raise falcon.errors.HTTPConflict('Conflict', 'Other content links to this')
                else:
                    raise

            resp.status = falcon.HTTP_OK
            req.context['result'] = {}

            after_delete = getattr(self, 'after_delete', None)
            if after_delete is not None:
                after_delete(req, resp, resource, *args, **kwargs)


    @falcon.before(identify)
    @falcon.before(authorize)
    def on_put(self, req, resp, *args, **kwargs):
        """
        Update an item in the collection.
        """
        if 'PUT' not in getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']))

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            resources = self.apply_arg_filter(req, resp, db_session.query(self.model), kwargs)

            resource = None
            try:
                resource = resources.one()
            except sqlalchemy.orm.exc.NoResultFound:
                if not getattr(self, 'allow_put_insert', False):
                    raise falcon.errors.HTTPNotFound()
            except sqlalchemy.orm.exc.MultipleResultsFound:
                self.logger.error('Programming error: multiple results found for put of model {0}'.format(self.model))
                raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')

            is_new = resource is None
            if is_new:
                attributes, _ = self.deserialize(self.model, kwargs, req.context['doc'], False)
                resource = self.model()
            else:
                attributes, _ = self.deserialize(self.model, {}, req.context['doc'], False)

            if len(attributes) > 1:
                raise falcon.errors.HTTPBadRequest('Invalid Request Body', 'Array bodies are only allowed with POST requests')
            attributes = attributes[0]

            self.apply_default_attributes('put_defaults', req, resp, attributes)

            for key, value in attributes.items():
                setattr(resource, key, value)

            db_session.add(resource)
            try:
                db_session.commit()
            except sqlalchemy.exc.IntegrityError as err:
                # Cases such as unallowed NULL value should have been checked
                # before we got here (e.g. validate against schema
                # using the middleware) - therefore assume this is a UNIQUE
                # constraint violation
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
            except sqlalchemy.exc.ProgrammingError as err:
                db_session.rollback()
                if self._is_unique_violation(err):
                    raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
                else:
                    raise
            except:
                db_session.rollback()
                raise

            resp.status = falcon.HTTP_CREATED if is_new else falcon.HTTP_OK
            req.context['result'] = {
                'data': self.serialize(resource, _get_response_fields(self, req, resp, resource, *args, **kwargs), getattr(self, 'geometry_axes', {})),
            }

            after_put = getattr(self, 'after_put', None)
            if after_put is not None:
                after_put(req, resp, resource, *args, **kwargs)

    def patch_precondition(self, req, resp, query, *args, **kwargs):
        return query

    def modify_patch(self, req, resp, resource, *args, **kwargs):
        pass

    @falcon.before(identify)
    @falcon.before(authorize)
    def on_patch(self, req, resp, *args, **kwargs):
        """
        Update part of an item in the collection.
        """
        if 'PATCH' not in getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']):
            raise falcon.errors.HTTPMethodNotAllowed(getattr(self, 'methods', ['GET', 'PUT', 'PATCH', 'DELETE']))

        with session_scope(self.db_engine, sessionmaker_=self.sessionmaker, **self.sessionmaker_kwargs) as db_session:
            resources = self.apply_arg_filter(req, resp, db_session.query(self.model), kwargs)

            try:
                resource = resources.one()
            except sqlalchemy.orm.exc.NoResultFound:
                raise falcon.errors.HTTPNotFound()
            except sqlalchemy.orm.exc.MultipleResultsFound:
                self.logger.error('Programming error: multiple results found for patch of model {0}'.format(self.model))
                raise falcon.errors.HTTPInternalServerError('Internal Server Error', 'An internal server error occurred')

            resources = self.patch_precondition(
                req, resp,
                self.filter_by_params(resources, req.params),
                *args, **kwargs
            )

            try:
                resource = resources.one()
            except sqlalchemy.orm.exc.NoResultFound:
                raise falcon.errors.HTTPConflict('Conflict', 'Resource found but conditions violated')

            attributes, _ = self.deserialize(self.model, {}, req.context['doc'], False)

            if len(attributes) > 1:
                raise falcon.errors.HTTPBadRequest('Invalid Request Body', 'Array bodies are only allowed with POST requests')
            attributes = attributes[0]

            self.apply_default_attributes('patch_defaults', req, resp, attributes)

            for key, value in attributes.items():
                setattr(resource, key, value)

            self.modify_patch(req, resp, resource, *args, **kwargs)

            before_patch = getattr(self, 'before_patch', None)
            if before_patch is not None:
                self.before_patch(req, resp, db_session, resource, *args, **kwargs)

            db_session.add(resource)
            try:
                db_session.commit()
            except sqlalchemy.exc.IntegrityError as err:
                # Cases such as unallowed NULL value should have been checked
                # before we got here (e.g. validate against schema
                # using the middleware) - therefore assume this is a UNIQUE
                # constraint violation
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
            except sqlalchemy.orm.exc.StaleDataError as err:
                # Version field in the model was not as expected
                db_session.rollback()
                raise falcon.errors.HTTPConflict('Conflict', 'Resource found but conditions violated')
            except sqlalchemy.exc.ProgrammingError as err:
                db_session.rollback()
                if self._is_unique_violation(err):
                    raise falcon.errors.HTTPConflict('Conflict', 'Unique constraint violated')
                else:
                    raise
            except:
                db_session.rollback()
                raise

            resp.status = falcon.HTTP_OK
            req.context['result'] = {
                'data': self.serialize(resource, _get_response_fields(self, req, resp, resource, *args, **kwargs), getattr(self, 'geometry_axes', {})),
            }

            after_patch = getattr(self, 'after_patch', None)
            if after_patch is not None:
                after_patch(req, resp, resource, *args, **kwargs)
