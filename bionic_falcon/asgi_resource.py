import falcon
from .resource import SingleResource, CollectionResource
from .resource import identify, authorize

async def async_identify(req, resp, resource, params):
    identify(req, resp, resource, params)

async def async_authorize(req, resp, resource, params):
    authorize(req, resp, resource, params)


class AsyncCollectionResource(CollectionResource):
    """
    Provides Async CRUD facilities for a resource collection.
    """

    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_get(self, req, resp, *args, **kwargs):
        """
        Return a collection of items.
        """
        super(AsyncCollectionResource, self).on_get(req, resp, *args, **kwargs)

    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_post(self, req, resp, *args, **kwargs):
        """
        Add an item to the collection.
        """
        super(AsyncCollectionResource, self).on_post(req, resp, *args, **kwargs)

    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_patch(self, req, resp, *args, **kwargs):
        """
        Update a collection.
        """
        super(AsyncCollectionResource, self).on_patch(req, resp, *args, **kwargs)
        

class AsyncSingleResource(SingleResource):
    """
    Provides CRUD facilities for a single resource.
    """

    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_get(self, req, resp, *args, **kwargs):
        """
        Return a single item.
        """
        super(AsyncSingleResource, self).on_get(req, resp, *args, **kwargs)


    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_delete(self, req, resp, *args, **kwargs):
        """
        Delete a single item.
        """
        super(AsyncSingleResource, self).on_delete(req, resp, *args, **kwargs)


    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_put(self, req, resp, *args, **kwargs):
        """
        Update an item in the collection.
        """
        super(AsyncSingleResource, self).on_put(req, resp, *args, **kwargs)


    @falcon.before(async_identify)
    @falcon.before(async_authorize)
    async def on_patch(self, req, resp, *args, **kwargs):
        """
        Update part of an item in the collection.
        """
        super(AsyncSingleResource, self).on_patch(req, resp, *args, **kwargs)
