# Falcon-AutoCRUD

Makes RESTful CRUD easier.

## Test status

[ ![Codeship Status for garymonson/falcon-autocrud](https://codeship.com/projects/ed5bb4c0-b517-0133-757f-3e023a4cadff/status?branch=master)](https://codeship.com/projects/134046)

## IMPORTANT CHANGE IN 1.0.0

Previously, the CollectionResource and SingleResource classes took db_session
as a parameter to the constructor.  As of 1.0.0, they now take db_engine
instead.  The reason for this is to keep the sessions short-lived and under
autocrud's control to explicitly close the sessions.

This WILL impact you as your routing should now pass the db_engine instead of
the db_session, and if you override these classes, then, if you have overridden
the constructor, you may also have to update that.

## Quick start for contributing

```
virtualenv -p `which python3` virtualenv
source virtualenv/bin/activate
pip install -r requirements.txt
pip install -r dev_requirements.txt
nosetests
```

This runs the tests with SQLite.  To run the tests with Postgres (using
pg8000), you must have a Postgres server running, and a postgres user with
permission to create databases:

```
export AUTOCRUD_DSN=postgresql+pg8000://myuser:mypassword@localhost:5432
nosetests
```

## Usage

Declare your SQLAlchemy models:

```
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, Integer, String

Base = declarative_base()

class Employee(Base):
    __tablename__ = 'employees'
    id      = Column(Integer, primary_key=True)
    name    = Column(String(50))
    age     = Column(Integer)
```

Declare your resources:

```
from falcon_autocrud.resource import CollectionResource, SingleResource

class EmployeeCollectionResource(CollectionResource):
    model = Employee

class EmployeeResource(SingleResource):
    model = Employee
```

Apply them to your app, ensuring you pass an SQLAlchemy engine to the resource
classes:

```
from sqlalchemy import create_engine
import falcon
import falconjsonio.middleware

db_engine = create_engine('sqlite:///stuff.db')

app = falcon.API(
    middleware=[
        falconjsonio.middleware.RequireJSON(),
        falconjsonio.middleware.JSONTranslator(),
    ],
)

app.add_route('/employees', EmployeeCollectionResource(db_engine))
app.add_route('/employees/{id}', EmployeeResource(db_engine))
```

This automatically creates RESTful endpoints for your resources:

```
http GET http://localhost/employees
http GET http://localhost/employees?name=Bob
http GET http://localhost/employees?age__gt=24
http GET http://localhost/employees?age__gte=25
http GET http://localhost/employees?age__lt=25
http GET http://localhost/employees?age__lte=24
http GET http://localhost/employees?name__contains=John
http GET http://localhost/employees?name__startswith=John
http GET http://localhost/employees?company_id__null=1
http GET http://localhost/employees?company_id__null=0
echo '{"name": "Jim"}' | http POST http://localhost/employees
http GET http://localhost/employees/100
echo '{"name": "Jim"}' | http PUT http://localhost/employees/100
echo '{"name": "Jim"}' | http PATCH http://localhost/employees/100
http DELETE http://localhost/employees/100
# PATCHing a collection to add entities in bulk
echo '{"patches": [{"op": "add", "path": "/", "value": {"name": "Jim"}}]}' | http PATCH http://localhost/employees
```

### Limiting methods

By default collections will autogenerate methods GET, POST and PATCH, while
single resources will autogenerate methods GET, PUT, PATCH, DELETE.

To limit which methods are autogenerated for your resource, simply list method
names as follows:

```
# Able to create and search collection:
class AccountCollectionResource(CollectionResource):
    model = Account
    methods = ['GET', 'POST']

# Only able to read individual accounts:
class AccountResource(CollectionResource):
    model = Account
    methods = ['GET']
```

### Pre-method functionality.

To do something before a POST or PATCH method is called, add special methods as
follows:

```
class AccountCollectionResource(CollectionResource):
    model = Account

    def before_post(self, req, resp, db_session, resource, *args, **kwargs):
      # Anything you do with db_session is in the same transaction as the
      # resource creation.  Resource is the new resource not yet added to the
      # database.
      pass

class AccountResource(SingleResource):
    model = Account

    def before_patch(self, req, resp, db_session, resource, *args, **kwargs):
      # Anything you do with db_session is in the same transaction as the
      # resource update.  Resource is the modified resource not yet saved to
      # the database.
      pass
```

### Post-method functionality

To do something after success of a method, add special methods as follows:

```
class AccountCollectionResource(CollectionResource):
    model = Account

    def after_get(self, req, resp, collection, *args, **kwargs):
        # 'collection' is the SQLAlchemy collection resulting from the search
        pass

    def after_post(self, req, resp, new, *args, **kwargs):
        # 'new' is the created SQLAlchemy instance
        pass

    def after_patch(self, req, resp, *args, **kwargs):
        pass


class AccountResource(CollectionResource):
    model = Account

    def after_get(self, req, resp, item, *args, **kwargs):
        # 'item' is the retrieved SQLAlchemy instance
        pass

    def after_put(self, req, resp, item, *args, **kwargs):
        # 'item' is the changed SQLAlchemy instance
        pass

    def after_patch(self, req, resp, item, *args, **kwargs):
        # 'item' is the patched SQLAlchemy instance
        pass

    def after_delete(self, req, resp, item, *args, **kwargs):
        pass
```

Be careful not to throw an exception in the above methods, as this will end up
propagating a 500 Internal Server Error.

### Modifying a patch

If you want to modify the patched resource before it is saved (e.g. to set
default values), you can override the default empty method in SingleResource:

```
class AccountResource(SingleResource):
    model = Account

    def modify_patch(self, req, resp, resource, *args, **kwargs):
        """
        Add 'arino' to people's names
        """
        resource.name = resource.name + 'arino'
```

### Identification and Authorization

Define classes that know how to identify and authorize users:

```
class TestIdentifier(object):
    def identify(self, req, resp, resource, params):
        req.context['user'] = req.get_header('Authorization')
        if req.context['user'] is None:
            raise HTTPUnauthorized('Authentication Required', 'No credentials supplied')

class TestAuthorizer(object):
    def authorize(self, req, resp, resource, params):
        if 'user' not in req.context or req.context['user'] != 'Jim':
            raise HTTPForbidden('Permission Denied', 'User does not have access to this resource')
```

Then declare which class identifies/authorizes what resource or method:

```
# Authorizes for all methods
@identify(TestIdentifier)
@authorize(TestAuthorizer)
class AccountCollectionResource(CollectionResource):
    model = Account

# Or only some methods
@identify(TestIdentifier)
@authorize(TestAuthorizer, methods=['GET', 'POST'])
@authorize(OtherAuthorizer, methods=['PATCH'])
class OtherAccountCollectionResource(CollectionResource):
    model = Account
```

### Filters/Preconditions

You may filter on GET, and set preconditions on single resource PATCH or DELETE:

```
class AccountCollectionResource(CollectionResource):
    model = Account

    def get_filter(self, req, resp, query, *args, **kwargs):
        # Only allow getting accounts below id 5
        return query.filter(Account.id < 5)

class AccountResource(SingleResource):
    model = Account

    def get_filter(self, req, resp, query, *args, **kwargs):
        # Only allow getting accounts below id 5
        return query.filter(Account.id < 5)

    def patch_precondition(self, req, resp, query, *args, **kwargs):
        # Only allow setting owner of non-owned account
        if 'owner' in req.context['doc'] and req.context['doc']['owner'] is not None:
            return query.filter(Account.owner == None)
        else:
            return query

    def delete_precondition(self, req, resp, query, *args, **kwargs):
        # Only allow deletes of non-owned accounts
        return query.filter(Account.owner == None)
```

### Not really deleting

If you want to just mark a resource as deleted in the database, but not really
delete the row, define a 'mark_deleted' in your SingleResource subclass:

```
class AccountResource(SingleResource):
    model = Account

    def mark_deleted(self, req, resp, instance, *args, **kwargs):
        instance.deleted = datetime.utcnow()
```

This will cause the changed instance to be updated in the database instead of
doing a DELETE.

Of course, the database row will still be accessible via GET, but you can
automatically filter out "deleted" rows like this:

```
class AccountCollectionResource(CollectionResource):
    model = Account

    def get_filter(self, req, resp, resources, *args, **kwargs):
        return resources.filter(Account.deleted == None)

class AccountResource(SingleResource):
    model = Account

    def get_filter(self, req, resp, resources, *args, **kwargs):
        return resources.filter(Account.deleted == None)

    def mark_deleted(self, req, resp, instance, *args, **kwargs):
        instance.deleted = datetime.utcnow()
```

You could also look at the request to only filter out "deleted" rows for some
users.

### Joins

If you want to add query parameters to your collection queries, that do not
refer to a resource attribute, but which refer to an attribute in a linked
table, you can do this in get_filter, as with the below example.  Ensure that
you remove the extra parameter value from req.params before returning from
get_filter, as falcon-autocrud will try (and fail) to look up the parameter in
the main resource class.

```
class Company(Base):
    __tablename__ = 'companies'
    id          = Column(Integer, primary_key=True)
    name        = Column(String(50), unique=True)
    employees   = relationship('Employee')

class Employee(Base):
    __tablename__ = 'employees'
    id          = Column(Integer, primary_key=True)
    name        = Column(String(50), unique=True)
    company_id  = Column(Integer, ForeignKey('companies.id'), nullable=True)
    company     = relationship('Company', back_populates='employees')

class EmployeeCollectionResource(CollectionResource):
    model = Employee

    def get_filter(self, req, resp, query, *args, **kwargs):
        if 'company_name' in req.params:
            company_name = req.params['company_name']
            del req.params['company_name']
            query = query.join(Employee.company).filter(Company.name == company_name)
        return query
```

Alternatively, for arguments that are part of the URL you may use attr_map directly:

```
class CompanyEmployeeCollectionResource(CollectionResource):
    model = Employee

    attr_map = {
        'company_id':   lambda req, resp, query, *args, **kwargs: query.join(Employee.company).filter(Company.id == kwargs['company_id'])
    }

```

This is useful for the following sort of URL:

```
GET /companies/{company_id}/employees
```

### Sorting

You can specify a default sorting of results from the collection search.  The
below example sorts firstly by name, then by salary descending:

```
class EmployeeCollectionResource(CollectionResource):
    model = Employee
    default_sort = ['name', '-salary']
```

The caller can specify a sort (which overrides the default if defined):

```
GET /path/to/collection?__sort=name,-salary
```

### Paging

The caller can specify an offset and/or limit to collection GET to provide
paging of search results.

```
GET /path/to/collection?__offset=10&limit=10
```

This is generally most useful in combination with __sort to ensure consistency
of sorting.

### Limiting response fields

You can limit which fields are returned to the client like this:

```
class EmployeeCollectionResource(CollectionResource):
    model = Employee
    fields = ['id', 'name']
```
