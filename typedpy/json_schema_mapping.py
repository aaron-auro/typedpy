from collections import OrderedDict

from typedpy.fields import StructureReference, Integer, Number, Float, Array, Enum, String, \
    ClassReference, Field, Boolean, \
    AllOf, OneOf, AnyOf, NotField


def as_str(val):
    return "'{}'".format(val) if isinstance(val, str) else val


def get_mapper(field_cls):
    field_type_to_mapper = {
        StructureReference: StructureReferenceMapper,
        Integer: IntegerMapper,
        Number: NumberMapper,
        Float: FloatMapper,
        Array: ArrayMapper,
        Enum: EnumMapper,
        String: StringMapper,
        AllOf: AllOfMapper,
        AnyOf: AnyOfMapper,
        OneOf: OneOfMapper,
        NotField: NotFieldMapper
    }
    return field_type_to_mapper[field_cls]


def convert_to_schema(field, definitions_schema):
    """
    In case field is None, should return None.
    Should deal with a list of fields, as well as a single one
    """
    if field is None:
        return None
    if isinstance(field, ClassReference):
        definition, _ = structure_to_schema(getattr(field, '_ty'), definitions_schema)
        name = getattr(field, '_ty').__name__
        definitions_schema[name] = definition
        return {'$ref': '#/definitions/{}'.format(name)}
    if isinstance(field, list):
        return [convert_to_schema(f, definitions_schema) for f in field]
    mapper = get_mapper(field.__class__)(field)
    return mapper.to_schema(definitions_schema)


def structure_to_schema(structure, definitions_schema):
    #json schema draft4 does not support inheritance, so we don't need to worry about that
    props = structure.__dict__
    fields = [key for key, val in props.items() if isinstance(val, Field)]
    required = props.get('_required', fields)
    additional_props = props.get('_additionalProperties', True)
    fields_schema = OrderedDict([('type', 'object')])
    fields_schema.update(OrderedDict([(key, convert_to_schema(props[key], definitions_schema))
                                      for key in fields]))
    fields_schema.update(OrderedDict([
        ('required', required),
        ('additionalProperties', additional_props),
    ]))
    return (fields_schema, definitions_schema)


def convert_to_field_code(schema, definitions):
    """
    In case schema is None, should return None.
    Should deal with a schema that is a dict, as well as one that is a list
    """

    if schema is None:
        return None
    if isinstance(schema, list):
        fields = [convert_to_field_code(s, definitions) for s in schema]
        return '[{}]'.format(', '.join(fields))
    if '$ref' in schema:
        def_name = schema['$ref'][len('#/definitions/'):]
        return def_name

    type_name_to_field = {
        'object': StructureReference,
        'integer': Integer,
        'number': Number,
        'float': Float,
        'array': Array,
        'enum': Enum,
        'string': String,
        'boolean': Boolean
    }
    multivals = {
        'allOf': AllOf,
        'anyOf': AnyOf,
        'oneOf': OneOf,
        'not': NotField
    }
    if any(multival in schema for multival in multivals):
        for (k, the_class) in multivals.items():
            if k in schema:
                cls = the_class
        mapper = MultiFieldMapper

    else:
        cls = type_name_to_field[schema.get('type', 'object')]
        mapper = get_mapper(cls)
    params_list = mapper.get_paramlist_from_schema(schema, definitions)
 #   print("param list: {} \n ".format(params_list))

    params_as_string = ", ".join(["{}={}".format(name, val) for (name, val) in params_list])
    return '{}({})'.format(cls.__name__, params_as_string)


def schema_to_struct_code(struct_name, schema, definitions_schema):
    """
    In case schema is None, should return None.
    Should deal with a schema that is a dict, as well as one that is a list
    """
    body = ['class {}(Structure):'.format(struct_name)]
    body += ['    _additionalProperties = False'] if not \
        schema.get('additionalProperties', True) else []
    required = schema.get('required', None)
    body += ['    _required = {}'.format(required)] if  required is not None else []
    fields = [(k, v) for (k, v) in schema.items() if k
              not in {'required', 'additionalProperties', 'type'}]
    for (name, sch) in fields:
        body += ['    {} = {}'.format(name, convert_to_field_code(sch, definitions_schema))]
    return '\n'.join(body)

def schema_definitions_to_code(schema):
    code = []
    for (name, sch) in schema.items():
        code.append(schema_to_struct_code(name, sch, schema))
    return '\n\n'.join(code)



class Mapper(object):
    def __init__(self, value):
        self.value = value

class StructureReferenceMapper(Mapper):

    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        body = []
        body += [('_additionalProperties', False)] if not \
            schema.get('additionalProperties', True) else []
        required = schema.get('required', None)
        body += [('_required', required)] if required is not None else []
        fields = [(k, v) for (k, v) in schema.items() if k
                  not in {'required', 'additionalProperties', 'type'}]

        body += [(k, convert_to_field_code(v, definitions)) for (k, v) in fields]
        return body

    def to_schema(self, definitions):
        schema, _ = structure_to_schema(getattr(self.value, '_newclass'), definitions)
        schema['type'] = 'object'
        return schema


class NumberMapper(Mapper):

    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        params = {
            'multiplesOf': schema.get('multiplesOf', None),
            'minimum': schema.get('minimum', None),
            'maximum': schema.get('maximum', None),
            'exclusiveMaximum': schema.get('exclusiveMaximum', None)
        }
        return list((k, v) for k, v in params.items() if v is not None)

    def to_schema(self, definitions):
        value = self.value
        params = {
            'type': 'number',
            'multiplesOf': value.multiplesOf,
            'minimum': value.minimum,
            'maximum': value.maximum,
            'exclusiveMaximum': value.exclusiveMaximum
        }
        return dict([(k, v) for k, v in params.items() if v is not None])


class IntegerMapper(NumberMapper):
    def to_schema(self, definitions):
        params = super().to_schema(definitions)
        params.update({'type': 'integer'})
        return params


class FloatMapper(NumberMapper):
    def to_schema(self, definitions):
        params = super().to_schema(definitions)
        params.update({'type': 'float'})
        return params


class BooleanMapper(object):

    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        return []

    def to_schema(self, definitions):  # pylint: disable=R0201
        params = {
            'type': 'boolean',
        }
        return params


class StringMapper(Mapper):

    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        params = {
            'minLength': schema.get('minLength', None),
            'maxLength': schema.get('maxLength', None),
            'pattern': as_str(schema.get('pattern', None)),
        }
        return list((k, v) for k, v in params.items() if v is not None)

    def to_schema(self, definitions):
        value = self.value
        params = {
            'type': 'string',
            'minLength': value.minLength,
            'maxLength': value.maxLength,
            'pattern': value.pattern
        }
        return dict([(k, v) for k, v in params.items() if v is not None])


class ArrayMapper(Mapper):

    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        items = schema.get('items', None)

        params = {
            'uniqueItems': schema.get('uniqueItems', None),
            'additionalItems': schema.get('additionalItems', None),
            'items': convert_to_field_code(items, definitions)
        }

        return list((k, v) for k, v in params.items() if v is not None)

    def to_schema(self, definitions):
        value = self.value
        params = {
            'type': 'array',
            'uniqueItems': value.uniqueItems,
            'additionalItems': value.additionalItems,
            'maxItems': value.maxItems,
            'minItems': value.minItems,
            'items': convert_to_schema(value.items, definitions)
        }
        return dict([(k, v) for k, v in params.items() if v is not None])


class EnumMapper(Mapper):

    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        params = {
            'values': schema.get('values', None),
        }
        return list(params.items())

    def to_schema(self, definitions):
        params = {
            'type': 'enum',
            'values': self.value.values
        }
        return dict([(k, v) for k, v in params.items() if v is not None])


class MultiFieldMapper(object):
    @staticmethod
    def get_paramlist_from_schema(schema, definitions):
        items = list(schema.values())[0]
        params = {
            'fields': convert_to_field_code(items, definitions)
        }
        return list(params.items())


class AllOfMapper(Mapper):

    def to_schema(self, definitions):
        return {'allOf': convert_to_schema(self.value._fields, definitions)}



class OneOfMapper(Mapper):
    def to_schema(self, definitions):
        return {'oneOf': convert_to_schema(self.value._fields, definitions)}



class AnyOfMapper(Mapper):
    def to_schema(self, definitions):
        return {'anyOf': convert_to_schema(self.value._fields, definitions)}



class NotFieldMapper(Mapper):
    def to_schema(self, definitions):
        return {'not': convert_to_schema(self.value._fields, definitions)}