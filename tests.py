from django.test import TestCase
import fudge
from jqgrid import JqGrid

class JqGridTest(TestCase):
    def setUp(self):
        self.jqgrid =  JqGrid()

    def test_get_filters_should_allow_empty_queries(self):
        request = fudge.Fake('request') 
        request.GET = {'_search': 'true', 
                'filters': '',
                'searchField': 'any',
                'searchOper' : 'gt',
                'searchString' : 'some string'}
        filters = self.jqgrid.get_filters(request)
        self.assertNotEquals(0,filters['rules'].__len__())

