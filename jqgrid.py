# Copyright (c) 2009, Gerry Eisenhaur
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    1. Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#
#    2. Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#
#    3. Neither the name of the project nor the names of its contributors may
#       be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import operator
from django.db import models
from django.core.exceptions import FieldError, ImproperlyConfigured,\
        ValidationError
from django.core.paginator import Paginator, InvalidPage
from django.core import serializers 
from django.utils.encoding import smart_str
from django.http import Http404
from django import forms
from decimal import Decimal
import json

django_json = serializers.get_serializer('json')()

class JqGrid(object):
    queryset = None
    model = None
    fields = []
    allow_empty = True
    extra_config = {}

    pager_id = '#pager'
    url = None
    edit_url = None
    caption = None
    colmodel_overrides = {}
    request = None
    form = None
    custom_widgets = {}

    def get_queryset(self):
        request = self.request
        if hasattr(self, 'queryset') and self.queryset is not None:
            queryset = self.queryset._clone()
        elif hasattr(self, 'model') and self.model is not None:
            queryset = self.model.objects.values(*self.get_field_names())
        else:
            raise ImproperlyConfigured("No queryset or model defined.")
        self.queryset = queryset
        return self.queryset

    def get_model(self):
        if hasattr(self, 'model') and self.model is not None:
            model = self.model
        elif hasattr(self, 'queryset') and self.queryset is not None:
            model = self.queryset.model
            self.model = model
        else:
            raise ImproperlyConfigured("No queryset or model defined.")
        return model

    def get_items(self):
        request = self.request
        items = self.get_queryset()
        items = self.filter_items(items)
        items = self.sort_items(items)
        paginator, page, items = self.paginate_items(items)
        return (paginator, page, items)

    def get_filters(self):
        request = self.request
        _search = request.GET.get('_search')
        filters = None

        if _search == 'true':
            _filters = request.GET.get('filters')
            try:
                filters = _filters and json.loads(_filters)
            except ValueError:
                return None

            if filters is None or filters == '':
                field = request.GET.get('searchField')
                op = request.GET.get('searchOper')
                data = request.GET.get('searchString')

                if all([field, op]):
                    filters = {
                        'groupOp': 'AND',
                        'rules': [{ 'op': op, 'field': field, 'data': data }]
                    }
        return filters

    def filter_items(self, items):
        # TODO: Add option to use case insensitive filters
        # TODO: Add more support for RelatedFields (searching and displaying)
        # FIXME: Validate data types are correct for field being searched.
        request = self.request
        filter_map = {
            # jqgrid op: (django_lookup, use_exclude)
            'ne': ('%(field)s__exact', True),
            'bn': ('%(field)s__startswith', True),
            'en': ('%(field)s__endswith',  True),
            'nc': ('%(field)s__contains', True),
            'ni': ('%(field)s__in', True),
            'in': ('%(field)s__in', False),
            'eq': ('%(field)s__exact', False),
            'bw': ('%(field)s__startswith', False),
            'gt': ('%(field)s__gt', False),
            'ge': ('%(field)s__gte', False),
            'lt': ('%(field)s__lt', False),
            'le': ('%(field)s__lte', False),
            'ew': ('%(field)s__endswith', False),
            'cn': ('%(field)s__contains', False)
        }
        _filters = self.get_filters()
        if _filters is None:
            return items

        q_filters = []
        for rule in _filters['rules']:
            op, field, data = rule['op'], rule['field'], rule['data']
            # FIXME: Restrict what lookups performed against RelatedFields
            field_class = self.get_model()._meta.get_field_by_name(field)[0]
            if isinstance(field_class, models.related.RelatedField):
                op = 'eq'
            filter_fmt, exclude = filter_map[op]
            filter_str = smart_str(filter_fmt % {'field': field})
            if filter_fmt.endswith('__in'):
                d_split = data.split(',')
                filter_kwargs = {filter_str: data.split(',')}
            else:
                filter_kwargs = {filter_str: smart_str(data)}

            if exclude:
                q_filters.append(~models.Q(**filter_kwargs))
            else:
                q_filters.append(models.Q(**filter_kwargs))

        if _filters['groupOp'].upper() == 'OR':
            filters = reduce(operator.ior, q_filters)
        else:
            filters = reduce(operator.iand, q_filters)
        return items.filter(filters)

    def sort_items(self, items):
        request = self.request
        sidx = request.GET.get('sidx')
        if sidx is not None:
            sord = request.GET.get('sord')
            order_by = '%s%s' % (sord == 'desc' and '-' or '', sidx)
            try:
                items = items.order_by(order_by)
            except FieldError:
                pass
        return items

    def get_paginate_by(self):
        rows = self.request.GET.get('rows', 10)
        try:
            paginate_by = int(rows)
        except ValueError:
            paginate_by = 10
        return paginate_by

    def paginate_items(self, items):
        request = self.request
        paginate_by = self.get_paginate_by()
        if not paginate_by:
            return (None, None, items)

        paginator = Paginator(items, paginate_by,
                              allow_empty_first_page=self.allow_empty)
        page = request.GET.get('page', 1)

        try:
            page_number = int(page)
            page = paginator.page(page_number)
        except (ValueError, InvalidPage):
            page = paginator.page(1)
        return (paginator, page, page.object_list)

    def get_json(self, request):
        self.request = request
        paginator, page, items = self.get_items()
        items = self.to_array(items)
        data = {
            'page': page.number,
            'total': paginator.num_pages,
            'rows': items,
            'records': paginator.count
        }
        return json.dumps(data, cls = DecimalEncoder)

    def to_array(self, items):
        return [item for item in items]

    def get_default_config(self):
        config = {
            'datatype': 'json',
            'autowidth': True,
            'forcefit': True,
            'shrinkToFit': True,
            'jsonReader': { 'repeatitems': False  },
            'rowNum': 10,
            'rowList': [10, 25, 50, 100],
            'sortname': 'id',
            'viewrecords': True,
            'sortorder': "asc",
            'pager': self.pager_id,
            'altRows': True,
            'gridview': True,
            'height': 'auto',
            'editurl': '' if self.edit_url is None else self.edit_url
            #'multikey': 'ctrlKey',
            #'multiboxonly': True,
            #'multiselect': True,
            #'toolbar': [False, 'bottom'],
            #'userData': None,
            #'rownumbers': False,
        }
        return config

    def get_url(self):
        return self.url

    def get_caption(self):
        if self.caption is None:
            opts = self.get_model()._meta
            self.caption = opts.verbose_name_plural.capitalize()
        return self.caption

    def get_config(self, as_json=True):
        self.must_have_form()
        config = self.get_default_config()
        config.update(self.extra_config)
        config.update({
            'url': self.get_url(),
            'caption': self.get_caption(),
            'colModel': self.get_colmodels(),
        })
        if as_json:
            config = json.dumps(config)
        return config

    def lookup_foreign_key_field(self, options, field_name):
        '''Make a field lookup converting __ into real models fields'''
        if '__' in field_name:
            fk_name, field_name = field_name.split('__', 1)
            fields = [f for f in options.fields if f.name == fk_name]
            if len(fields) > 0:
                field_class = fields[0]
            else:
                raise FieldError('No field %s in %s' % (fk_name, options))
            foreign_model_options = field_class.rel.to._meta
            return self.lookup_foreign_key_field(foreign_model_options, field_name)
        else:
            return options.get_field_by_name(field_name)

    def get_colmodels(self):
        colmodels = []
        opts = self.get_model()._meta
        for field_name in self.get_field_names():
            (field, model, direct, m2m) = self.lookup_foreign_key_field(opts, field_name)
            colmodel = self.field_to_colmodel(field, field_name)
            override = self.colmodel_overrides.get(field_name)
            if override:
                colmodel.update(override)
            self.get_edit_info_from_field(colmodel, field_name)
            colmodels.append(colmodel)
        return colmodels

    def get_edit_info_from_field(self, colmodel, field_name):
        self.custom_widgets.update({
                forms.widgets.CheckboxInput: 'checkbox',
                forms.widgets.DateInput: 'text',
                forms.widgets.DateTimeInput: 'text',
                forms.widgets.HiddenInput: 'hidden',
                forms.widgets.PasswordInput: 'password',
                forms.widgets.RadioInput: 'radio',
                forms.widgets.TextInput: 'text',
                forms.widgets.Select: 'select',
                forms.widgets.FileInput: 'file',
                forms.widgets.Textarea: 'textarea',
                })
        widget_equivalence_table = self.custom_widgets
        try:
            widget = self.form().fields[field_name].widget
            field = widget.__class__
            colmodel['edittype'] = widget_equivalence_table[field]
            colmodel['editoptions'] = widget.attrs
            self.get_editoptions_from_field(colmodel, field_name)
        except KeyError:
            colmodel['edittype'] = 'text'

    def get_editoptions_from_field(self, colmodel, field_name):
        model_field = [f for f in self.get_model()._meta.fields if f.name==field_name]
        choices = dict(model_field[0].choices)
        colmodel['editoptions']['value'] = {}
        if choices.__len__() > 0:
            for c in choices.keys():
                colmodel['editoptions']['value'][c] = choices[c]
        #look for foreign key
        if model_field[0].rel is not None:
            related_model = model_field[0].rel.to
            choices = related_model.objects.all()
            for c in choices:
                colmodel['editoptions']['value'][str(c.id)] = str(c)

        if colmodel['editoptions']['value'] == {}:
            del colmodel['editoptions']['value']

    def get_field_names(self):
        fields = self.fields
        if not fields:
            fields = [f.name for f in self.get_model()._meta.fields]
        return fields

    def field_to_colmodel(self, field, field_name):
        editable = not isinstance(field, models.fields.AutoField)
        colmodel = {
            'name': field_name,
            'index': field.name,
            'label': field.verbose_name if type(field.verbose_name) == str else field.verbose_name.__unicode__(),
            'editable': editable 
        }
        return colmodel

    def handle_edit(self, request):
        self.must_have_form()
        self.request = request
        self.validate_edit_data()
        form = self.fill_form()

        if not form.is_valid():
            return_data = {'ok':False, 'errors': form.errors}
        else:
            if request.POST['oper'] == 'del':
                self.entry.delete()
                return_data = {'ok': True}
            else:
                entry = form.save()
                return_data = {'ok': True, 'id': entry.id }

        return json.dumps(return_data)
    
    def must_have_form(self):
        if self.form is None:
            msg = 'No form defined'
            raise ImproperlyConfigured(msg)

    def validate_edit_data(self):
        request = self.request
        if request.method != 'POST':
            raise ValidationError('This method only handle POST requests')

        self.is_edit_op = request.POST['oper'] in ('edit', 'del')

        if not request.POST.has_key('id') and self.is_edit_op:
            raise ValidationError('Missing object pk')
        if request.POST['oper'] not in ('edit', 'del', 'add'):
            raise ValidationError('Unknown operation')

        if self.is_edit_op:
            obj_id = request.POST['id']
            entry = self.get_model().objects.filter(id = obj_id)
            if entry.__len__() == 0 and request.POST['oper'] in ('edit', 'del'):
                raise ValidationError('There is no such object with id %s'%obj_id)
            self.entry = entry[0]

    def fill_form(self):
        data = self.request.POST
        if self.is_edit_op:
            obj_id = self.request.POST['id']
            entry = self.entry
            for field in self.get_field_names():
                if field not in data:
                    data[field] = getattr(entry, field)
            form = self.form(data, instance = entry)
        else:
            form = self.form(data)
        return form

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if (isinstance(obj, Decimal)):
            return str(obj).replace('.',',')
        return json.JSONEncoder.default(self, obj)
