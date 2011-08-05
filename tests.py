from django.test import TestCase
import fudge
from jqgrid import JqGrid
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.contrib.auth.models import User
from django.forms import ModelForm
import json

class JqGridTest(TestCase):

    def setUp(self):
        self.jqgrid =  JqGrid()
        self.request = fudge.Fake('request')
        User.objects.create(username='user1', password = '123')
        User.objects.create(username='user2', password = '123')
        User.objects.create(username='user3', password = '123')
        self.jqgrid.model = User

    def test_get_filters_should_allow_empty_queries(self):
        self.request.GET = {'_search': 'true', 
                'filters': '',
                'searchField': 'any',
                'searchOper' : 'gt',
                'searchString' : 'some string'}
        self.jqgrid.request = self.request
        filters = self.jqgrid.get_filters()
        self.assertNotEquals(0,filters['rules'].__len__())


    def test_it_should_not_handle_get_requests_in_edit(self):
        """JqGrid sends insert, edit and delete via post requests"""
        self.request.method = 'GET'
        self.jqgrid.form = UserForm
        try:
            self.jqgrid.handle_edit(self.request)
            self.fail('It should raise an validation error')
        except ValidationError:
            pass

    def test_it_should_raise_exception_if_theres_no_form_at_edit(self):
        self.request.method = 'POST'
        try:
            self.jqgrid.handle_edit(self.request)
            self.fail('ImproperlyConfigured sould be raised at this point')
        except ImproperlyConfigured:
            pass


    def test_it_should_raise_an_validation_error_on_unknown_op(self):
        self.request.method = 'POST'
        self.request.POST = {'oper': 'invalid_op'}
        self.jqgrid.form = UserForm
        try:
            self.jqgrid.handle_edit(self.request)
            self.fail('It should raise an validation error')
        except ValidationError:
            pass
    def test_it_should_raises_validation_error_at_edit_delete_with_noid(self):
        self.request.method = 'POST'
        self.request.POST = {'oper': 'edit'}
        self.jqgrid.form = UserForm
        try:
            self.jqgrid.handle_edit(self.request)
            self.fail('It should raise an validation error')
        except ValidationError:
            pass

    def test_it_should_raises_validation_error_on_edit_nonexistent(self):
        self.request.method = 'POST'
        self.request.POST = {'oper': 'edit', 'id': 999, 'name': 'tehname'}
        self.jqgrid.model = User
        self.jqgrid.form = UserForm
        try:
            self.jqgrid.handle_edit(self.request)
            self.fail('It should raise an validation error')
        except ValidationError:
            pass

    def test_it_should_return_json_with_error_when_form_is_invalid(self):
        self.request.method = 'POST'
        self.request.POST = {'oper': 'add'} 
        self.jqgrid.model = User
        self.jqgrid.form = UserForm
        response = json.loads(self.jqgrid.handle_edit(self.request))
        self.assertFalse(response['ok'])

    def test_it_should_return_no_error_when_the_add_form_is_valid(self):
        self.request.method = 'POST'
        self.request.POST = {
                'oper': 'add',
                'username': 'user4',
                'password': 'passwd',
                'date_joined': '2011-01-01',
                'last_login': '2011-01-01',
                }
        self.jqgrid.model = User
        self.jqgrid.form = UserForm
        response = json.loads(self.jqgrid.handle_edit(self.request))
        self.assertTrue(response['ok'])

    def test_it_should_update_the_record_when_the_form_is_valid(self):
        self.request.method = 'POST'
        self.request.POST = {
                'oper': 'edit',
                'id':'1',
                'username': 'anotherusername',
                }
        self.jqgrid.model = User
        self.jqgrid.form = UserForm
        response = json.loads(self.jqgrid.handle_edit(self.request))
        username = User.objects.filter(id = 1)[0].username
        self.assertEquals('anotherusername', username)

    def test_it_should_not_update_the_record_with_invalid_data(self):
        self.request.method = 'POST'
        self.request.POST = {
                'oper': 'edit',
                'id':'2',
                'username': 'user1', #duplicated user 
                }
        self.jqgrid.model = User
        self.jqgrid.form = UserForm
        response = json.loads(self.jqgrid.handle_edit(self.request))
        self.assertFalse(response['ok'])

    def test_it_should_delete_when_the_registry_exists(self):
        self.request.method = 'POST'
        self.request.POST = {
                'oper': 'del',
                'id':'2',
                }
        self.jqgrid.model = User
        self.jqgrid.form = UserForm
        response = json.loads(self.jqgrid.handle_edit(self.request))
        user2 = User.objects.filter(id = 2)
        self.assertEquals(0, len(user2))

    def test_it_should_not_make_the_ids_editable_by_default(self):
        self.request.method = 'GET'
        self.request.GET = {}
        self.jqgrid.form = UserForm
        self.jqgrid.model = User
        config = json.loads(self.jqgrid.get_config(self.request))
        col_id = config['colModel'][0]
        self.assertTrue(col_id['index'] == 'id' and col_id['editable'] == False)

    def test_it_should_return_the_right_field_type_based_on_form(self):
        self.request.method = 'GET'
        self.jqgrid.form = UserForm
        self.jqgrid.model = User
        self.request.GET = {}
        config = json.loads(self.jqgrid.get_config(self.request))
        self.assertEquals('text', config['colModel'][0]['edittype'])
        self.assertEquals('text', config['colModel'][1]['edittype'])
        self.assertEquals('checkbox', config['colModel'][8]['edittype'])

class UserForm(ModelForm):
    class Meta:
        model = User
