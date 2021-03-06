"""
Definitions of various types of fields. Supports JSON draft4 types.
"""
import re
from collections import OrderedDict
from datetime import datetime
from functools import reduce

from typedpy.structures import Field, Structure, TypedField, ClassReference


class StructureReference(Field):
    """
    A Field that is an embedded structure within other structure. Allows to create hierarchy.
    This is useful if you want to inline your Structure, as opposed to create an explicit
    class for it.
    All the arguments are passed as attributes of the structure. Example:

    .. code-block:: python

        StructureReference(
            _additionalProperties = False,
            id = String,
            name = String
            age = AnyOf[PositiveInt, PositiveFloat]
        )

    """
    counter = 0

    def __init__(self, **kwargs):
        classname = "StructureReference_" + str(StructureReference.counter)
        StructureReference.counter += 1

        self._newclass = type(classname, (Structure,), kwargs)
        super().__init__(kwargs)

    def __set__(self, instance, value):
        if not isinstance(value, dict):
            raise TypeError("{}: Expected a dictionary".format(self._name))
        newval = self._newclass(**value)
        super().__set__(instance, newval)

    def __str__(self):
        props = []
        for k, val in sorted(self._newclass.__dict__.items()):
            if val is not None and not k.startswith('_'):
                props.append('{} = {}'.format(k, str(val)))

        propst = '. Properties: {}'.format(', '.join(props)) if props  else ''
        return '<Structure{}>'.format(propst)


class ImmutableField(Field):
    _immutable = True


class Number(Field):
    """
    Base class for numerical fields. Based on Json schema draft4.
    Accepts and int or float.

    Arguments:
        multipleOf(int): optional
            The number must be a multiple of this number
        minimum(int or float): optional
            value cannot be lower than this number
        maximum(int or float): optional
            value cannot be higher than this number
        exclusiveMaximum(bool): optional
            marks the maximum threshold above as exclusive

    """

    def __init__(self, *args, multiplesOf=None, minimum=None,
                 maximum=None, exclusiveMaximum=None, **kwargs):
        self.multiplesOf = multiplesOf
        self.minimum = minimum
        self.maximum = maximum
        self.exclusiveMaximum = exclusiveMaximum
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        def is_number(val):
            return isinstance(val, (float, int))

        if not isinstance(value, float) and not isinstance(value, int):
            raise TypeError("{}: Expected a number".format(self._name))
        if isinstance(self.multiplesOf, float) and \
                        int(value / self.multiplesOf) != value / self.multiplesOf or \
                        isinstance(self.multiplesOf, int) and value % self.multiplesOf:
            raise ValueError("{}: Expected a a multiple of {}".format(
                self._name, self.multiplesOf))
        if (is_number(self.minimum)) and self.minimum > value:
            raise ValueError("{}: Expected a minimum of {}".format(
                self._name, self.minimum))
        if is_number(self.maximum):
            if self.exclusiveMaximum and self.maximum == value:
                raise ValueError("{}: Expected a maxmimum of less than {}".format(
                    self._name, self.maximum))
            else:
                if self.maximum < value:
                    raise ValueError("{}: Expected a maxmimum of {}".format(
                        self._name, self.maximum))
        super().__set__(instance, value)


class Integer(TypedField, Number):
    """
    An extension of :class:`Number` for an integer. Accepts int
    """
    _ty = int



class String(TypedField):
    """
      A string value. Accepts input of `str`

      Arguments:
          minLength(int): optional
              minimal length
          maxLength(int): optional
              maximal lengthr
          pattern(str): optional
              string of a regular expression

      """
    _ty = str

    def __init__(self, *args, minLength=None, maxLength=None,
                 pattern=None, **kwargs):
        self.minLength = minLength
        self.maxLength = maxLength
        self.pattern = pattern
        if self.pattern is not None:
            self._compiled_pattern = re.compile(self.pattern)
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if not isinstance(value, str):
            raise TypeError("{}: Expected a string".format(self._name))
        if self.maxLength is not None and len(value) > self.maxLength:
            raise ValueError("{}: Expected a maxmimum length of {}".format(
                self._name, self.maxLength))
        if self.minLength is not None and len(value) < self.minLength:
            raise ValueError("{}: Expected a minimum length of {}".format(
                self._name, self.minLength))
        if self.pattern is not None and not self._compiled_pattern.match(value):
            raise ValueError('{}: Does not match regular expression: "{}"'.format(
                self._name, self.pattern))

        super().__set__(instance, value)


class Float(TypedField, Number):
    """
    An extension of :class:`Number` for a float
    """
    _ty = float


class Boolean(TypedField):
    """
    Value of type bool. True or False.
    """
    _ty = bool


class Positive(Number):
    """
    An extension of :class:`Number`. Requires the number to be positive
    """
    def __set__(self, instance, value):
        if value <= 0:
            raise ValueError('{}: Must be positive'.format(self._name))
        super().__set__(instance, value)


class PositiveFloat(Float, Positive):
    """
    An combination of :class:`Float` and :class:`Positive`
    """
    pass


class PositiveInt(Integer, Positive):
    """
       An combination of :class:`Integer` and :class:`Positive`
       """
    pass


class _ListStruct(list):
    """
    This is a useful wrapper for the content of list in an Array field.
    It ensures that an update of the form:
     mystruct.my_array[i] = new_val
    Will not bypass the validation of the Array.
    """

    def __init__(self, array, struct_instance, mylist):
        self._array = array
        self._instance = struct_instance
        super().__init__(mylist)

    def __setitem__(self, key, value):
        copied = self.copy()
        copied.__setitem__(key, value)
        setattr(self._instance, getattr(self._array, '_name', None), copied)

    def append(self, value):
        copied = self.copy()
        copied.append(value)
        setattr(self._instance, getattr(self._array, '_name', None), copied)

    def extend(self, value):
        copied = self.copy()
        copied.extend(value)
        setattr(self._instance, getattr(self._array, '_name', None), copied)

    def insert(self, index: int, value):
        copied = self.copy()
        copied.insert(index, value)
        setattr(self._instance, getattr(self._array, '_name', None), copied)

    def remove(self, ind):
        copied = self.copy()
        copied.remove(ind)
        setattr(self._instance, getattr(self._array, '_name', None), copied)

    def pop(self, index: int = -1):
        copied = self.copy()
        res = copied.pop(index)
        setattr(self._instance, getattr(self._array, '_name', None), copied)
        return res


class _DictStruct(dict):
    """
    This is a useful wrapper for the content of dict in an Map field.
    It ensures that an update of the form:
     mystruct.my_map[i] = new_val, or
     mystruct.my_map.update(some_dict)

    ...will not bypass the validation of the Map.
    """

    def __init__(self, the_map, struct_instance, mydict):
        self._map = the_map
        self._instance = struct_instance
        super().__init__(mydict)

    def __setitem__(self, key, value):
        copied = self.copy()
        copied.__setitem__(key, value)
        setattr(self._instance, getattr(self._map, '_name', None), copied)

    def __delitem__(self, key):
        copied = self.copy()
        del copied[key]
        setattr(self._instance, getattr(self._map, '_name', None), copied)

    def update(self, *args, **kwargs):
        copied = self.copy()
        res = copied.update(*args, **kwargs)
        setattr(self._instance, getattr(self._map, '_name', None), copied)
        return res


class _CollectionMeta(type):
    def __getitem__(cls, item):
        def validate_and_get_field(val):
            if isinstance(val, Field):
                return val
            elif Field in val.__mro__:
                return val()
            elif Structure in val.__mro__:
                return ClassReference(val)
            else:
                raise TypeError("Expected a Field class or instance")

        if isinstance(item, tuple):
            items = [validate_and_get_field(it) for it in item]
            return cls(items=items)
        return cls(items=validate_and_get_field(item))


class _EnumMeta(type):
    def __getitem__(cls, values):
        return cls(values=list(values))


class _JSONSchemaDraft4ReuseMeta(type):
    def __getitem__(cls, item):
        def validate_and_get_field(val):
            if isinstance(val, Field):
                return val
            elif Field in val.__mro__:
                return val()
            elif Structure in val.__mro__:
                return ClassReference(val)
            else:
                raise TypeError("Expected a Field class or instance")

        if isinstance(item, tuple):
            fields = [validate_and_get_field(it) for it in item]
            return cls(fields)
        return cls([validate_and_get_field(item)])


class SizedCollection(object):
    def __init__(self, *args, minItems=None, maxItems=None, **kwargs):
        self.minItems = minItems
        self.maxItems = maxItems
        super().__init__(*args, **kwargs)

    def validate_size(self, items, name):
        if self.minItems is not None and len(items) < self.minItems:
            raise ValueError("{}: Expected length of at least {}".format(
                name, self.minItems))
        if self.maxItems is not None and len(items) > self.maxItems:
            raise ValueError("{}: Expected length of at most {}".format(
                name, self.maxItems))


class Set(SizedCollection, TypedField, metaclass=_CollectionMeta):
    """
    A set collection. Accepts input of type `set`

    Arguments:
        minItems(int): optional
            minimal size
        maxItems(int): optional
            maximal size
        items(:class:`Field` or :class:`Structure`): optional
            The type of the content, can be a predefined :class:`Structure` or
            :class:`Field`

    Examples:

    .. code-block:: python

        Set[String]
        Set(items=Integer(maximum=10), maxItems = 10)


    """
    _ty = set

    def __init__(self, *args, items=None,
                 **kwargs):
        if items is None or isinstance(items, Field):
            self.items = items
        elif Field in getattr(items, '__mro__', []):
            self.items = items()
        else:
            raise TypeError("Expected a Field class or instance")

        if isinstance(self.items, TypedField) and not \
                getattr(getattr(self.items, '_ty'), '__hash__'):
            raise TypeError("Set element of type {} is not hashable".format(
                getattr(self.items, '_ty')))
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if not isinstance(value, set):
            raise TypeError("%s: Expected %s" % (self._name, set))
        self.validate_size(value, self._name)
        if self.items is not None:
            temp_st = Structure()
            setattr(self.items, '_name', self._name)
            res = set()
            for val in value:
                self.items.__set__(temp_st, val)
                res.add(getattr(temp_st, getattr(self.items, '_name')))
                value = res
        super().__set__(instance, value)


class Map(SizedCollection, TypedField, metaclass=_CollectionMeta):
    """
    A map/dictionary collection. Accepts input of type `dict`

    Arguments:
        minItems(int): optional
            minimal size
        maxItems(int): optional
            maximal size
        items(tuple of 2 :class:`Field` or :class:`Structure`  elements): optional
            The first element is the Field for keys, the second is for values.
            Examples:

            .. code-block:: python

                age_by_name = Map[String, PositiveInt]
                # Let's assume we defined a Structure "Person"
                person_by_id = Map[String, Person]

    """

    _ty = dict

    def __init__(self, *args, items=None,
                 **kwargs):
        if items is not None and (not isinstance(items, (tuple, list)) or len(items) != 2):
            raise TypeError("items is expected to be a list/tuple of two fields")
        if items is None:
            self.items = None
        else:
            self.items = []
            for item in items:
                if isinstance(item, Field):
                    self.items.append(item)
                elif Field in item.__mro__:
                    self.items.append(item())
                else:
                    raise TypeError("Expected a Field class or instance")
            key_field = self.items[0]
            if isinstance(key_field, TypedField) and not getattr(getattr(key_field, '_ty'), '__hash__'):
                raise TypeError("Key field of type {} is not hashable".format(
                    getattr(key_field, '_ty')))
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if not isinstance(value, dict):
            raise TypeError("%s: Expected %s" % (self._name, dict))
        self.validate_size(value, self._name)

        if self.items is not None:
            temp_st = Structure()
            key_field, value_field = self.items[0], self.items[1]
            setattr(key_field, '_name', self._name + '_key')
            setattr(value_field, '_name', self._name + '_value')
            res = OrderedDict()

            for key, val in value.items():
                key_field.__set__(temp_st, key)
                value_field.__set__(temp_st, val)
                res[getattr(temp_st, getattr(key_field, '_name'))] = getattr(
                    temp_st, getattr(value_field, '_name'))
            value = res

        super().__set__(instance, _DictStruct(self, instance, value))


class Array(SizedCollection, TypedField, metaclass=_CollectionMeta):
    """
    An Array field, similar to a list. Supports the properties in JSON schema draft 4.
    Expected input is of type `list`.

    Arguments:
        minItems(int): optional
            minimal size
        maxItems(int): optional
            maximal size
        unqieItems(bool): optional
            are elements required to be unique?
        additionalItems(bool): optional
            Relevant in case items parameter is a list of Fields. Is it allowed to have additional
            elements beyond the ones defined in "items"?
        items(a :class:`Field` or :class:`Structure`, or a list/tuple of :class:`Field` or :class:`Structure`): optional
            Describes the fields of the elements.
            If a items if a :class:`Field`, then it applies to all items.
            If a items is a list, then every element in the content is expected to be
            of the corresponding field in items.
            Examples:

            .. code-block:: python

                names = Array[String]
                names = Array[String(minLengh=3)]
                names = Array(minItems=5, items=String)
                my_record = Array(items=[String, Integer(minimum=5), String])
                my_lists = Array[Array[Integer]]
                my_structs = Array[StructureReference(a=Integer, b=Float)]
                # Let's say we defined a Structure "Person"
                people = Array[Person]

    """
    _ty = list

    def __init__(self, *args, items=None, uniqueItems=None, additionalItems=None,
                 **kwargs):
        """
        Constructor
        :param args: pass-through
        :param items: either a single field, which will be enforced for all elements, or a list
         of fields which enforce the elements with the correspondent index
        :param uniqueItems: are elements required to be unique?
        :param additionalItems: Relevant if "items" is a list. Is it allowed to have additional
        elements beyond the ones defined in "items"?
        :param kwargs: pass-through
        """
        self.uniqueItems = uniqueItems
        self.additionalItems = additionalItems
        if isinstance(items, list):
            self.items = []
            for item in items:
                if isinstance(item, Field):
                    self.items.append(item)
                elif Field in item.__mro__:
                    self.items.append(item())
                else:
                    raise TypeError("Expected a Field class or instance")
        else:
            self.items = items
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if not isinstance(value, list):
            raise TypeError("%s: Expected %s" % (self._name, list))
        self.validate_size(value, self._name)
        if self.uniqueItems:
            unique = reduce(lambda unique_vals, x: unique_vals.append(x) or
                            unique_vals if x not in unique_vals
                            else unique_vals, value, [])
            if len(unique) < len(value):
                raise ValueError("{}: Expected unique items".format(self._name))
        if self.items is not None:
            if isinstance(self.items, Field):
                temp_st = Structure()
                setattr(self.items, '_name', self._name)
                res = []
                for i, val in enumerate(value):
                    setattr(self.items, '_name', self._name + "_{}".format(str(i)))
                    self.items.__set__(temp_st, val)
                    res.append(getattr(temp_st, getattr(self.items, '_name')))
                value = res
            elif isinstance(self.items, list):
                additional_properties_forbidden = self.additionalItems is not None and \
                                                  self.additionalItems is False
                if len(self.items) > len(value) or \
                        (additional_properties_forbidden and len(self.items) > len(value)):
                    raise ValueError("{}: Expected an array of length {}".format(
                        self._name, len(self.items)))
                temp_st = Structure()
                res = []
                for ind, item in enumerate(self.items):
                    setattr(item, '_name', self._name + "_{}".format(str(ind)))
                    item.__set__(temp_st, value[ind])
                    res.append(getattr(temp_st, getattr(item, '_name')))
                res += value[len(self.items):]
                value = res

        super().__set__(instance, _ListStruct(self, instance, value))



class Tuple(TypedField, metaclass=_CollectionMeta):
    """
    A tuple field, supports unique items option.
       Expected input is of type `tuple`.

    Arguments:

        unqieItems(`bool`): optional
            are elements required to be unique?

        items(`list`/`tuple` of :class:`Field` or :class:`Structure`): optional
            Describes the fields of the elements.
            Every element in the content is expected to be
            of the corresponding :class:`Field` in items.

    Examples:

    .. code-block:: python

        a = Tuple(uniqueItems=True, items = [String, String])
        b = Tuple(items = [String, String, Number(maximum=10)])
        c = Tuple[Integer, String, Float]

    """
    _ty = tuple

    def __init__(self, *args, items, uniqueItems=None,
                 **kwargs):
        """
        Constructor
        :param args: pass-through
        :param items: either a single field, which will be enforced for all elements, or a list
         of fields which enforce the elements with the correspondent index
        :param uniqueItems: are elements required to be unique?
        :param kwargs: pass-through
        """
        self.uniqueItems = uniqueItems
        if isinstance(items, (list, tuple)):
            self.items = []
            for item in items:
                if isinstance(item, Field):
                    self.items.append(item)
                elif Field in item.__mro__:
                    self.items.append(item())
                else:
                    raise TypeError("Expected a Field class or instance")
        else:
            raise TypeError("Expected a list/tuple of Fields")
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if not isinstance(value, tuple):
            raise TypeError("%s: Expected %s" % (self._name, tuple))
        if self.uniqueItems:
            unique = reduce(lambda unique_vals, x: unique_vals.append(x) or
                            unique_vals if x not in unique_vals
                            else unique_vals, value, [])
            if len(unique) < len(value):
                raise ValueError("{}: Expected unique items".format(self._name))
        if len(self.items) != len(value):
            raise ValueError("{}: Expected a tuple of length {}".format(
                self._name, len(self.items)))

        temp_st = Structure()
        res = []
        for ind, item in enumerate(self.items):
            setattr(item, '_name', self._name + "_{}".format(str(ind)))
            item.__set__(temp_st, value[ind])
            res.append(getattr(temp_st, getattr(item, '_name')))
            res += value[len(self.items):]
        value = tuple(res)

        super().__set__(instance, value)



class Enum(Field, metaclass=_EnumMeta):
    """
        Enum field. value can be one of predefined values

        Arguments:
             values(`list` or `set` or `tuple`):
                 allowed values. Can be of any type

    """
    def __init__(self, *args, values, **kwargs):
        self.values = values
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if value not in self.values:
            raise ValueError('{}: Must be one of {}'.format(self._name, self.values))
        super().__set__(instance, value)



class EnumString(Enum, String):
    """
    Combination of :class:`Enum` and :class:`String`. This is useful if you want to further
    limit your allowable enum values, using :class:`String` attributes, such as pattern, maxLength.

    Example:

    .. code-block:: python

        predefined_list = ['abc', 'x', 'def', 'yy']

        EnumString(values=predefined_list, minLength=3)

    """
    pass


class DateString(TypedField):
    """
    A string field of the format '%Y-%m-%d' that can be converted to a date
    """
    _ty = str

    def __set__(self, instance, value):
        super().__set__(instance, value)
        try:
            datetime.strptime(value, '%Y-%m-%d')
        except ValueError as ex:
            raise ValueError("{}: {}".format(self._name, ex.args[0]))




class Sized(Field):
    """
    The length of the value is limited to be at most the maximum given.
    The value can be any iterable.

        Arguments:

            maxlen(`int`):
                maximum length

    """
    def __init__(self, *args, maxlen, **kwargs):
        self.maxlen = maxlen
        super().__init__(*args, **kwargs)

    def __set__(self, instance, value):
        if len(value) > self.maxlen:
            raise ValueError('{}: Too long'.format(self._name))
        super().__set__(instance, value)


class SizedString(String, Sized):
    pass


def _str_for_multioption_field(instance):
    name = instance.__class__.__name__
    if instance.get_fields():
        fields_st = ', '.join([str(field) for field in instance.get_fields()])
        propst = ' [{}]'.format(fields_st)
    else:
        propst = ''
    return '<{}{}>'.format(name, propst)


class MultiFieldWrapper(object):
    """
    An abstract base class for AllOf, AnyOf, OneOf, etc.
    It provides flexibility in reading the "fields" argument.
    """
    def __init__(self, *arg, fields, **kwargs):
        if isinstance(fields, list):
            self._fields = []
            for item in fields:
                if isinstance(item, Field):
                    self._fields.append(item)
                elif Field in item.__mro__:
                    self._fields.append(item())
                else:
                    raise TypeError("Expected a Field class or instance")
        else:
            raise TypeError("Expected a Field class or instance")
        super().__init__(*arg, **kwargs)

    def get_fields(self):
        return self._fields


class AllOf(MultiFieldWrapper, Field, metaclass=_JSONSchemaDraft4ReuseMeta):
    """
    Content must adhere to all requirements in the fields arguments.
    Arguments:

        fields( `list` of :class:`Field`): optional
        the content should match all of the fields in the list

    Example:

    .. code-block:: python

        AllOf[Number(maximum=20, minimum=-10), Integer, Positive]

    """
    def __init__(self, fields):
        super().__init__(fields=fields)

    def __set__(self, instance, value):
        for field in self.get_fields():
            setattr(field, '_name', self._name)
            field.__set__(instance, value)
        super().__set__(instance, value)

    def __str__(self):
        return _str_for_multioption_field(self)



class AnyOf(MultiFieldWrapper, Field, metaclass=_JSONSchemaDraft4ReuseMeta):
    """
    Content must adhere to one or more of the requirements in the fields arguments.
    Arguments:

        fields( `list` of :class:`Field`): optional
        the content should match at least one of the fields in the list

    Example:

    .. code-block:: python

       AnyOf[Number(maximum=20, minimum=-10), Integer, Positive, String]

    """
    def __init__(self, fields):
        super().__init__(fields=fields)

    def __set__(self, instance, value):
        matched = False
        for field in self.get_fields():
            setattr(field, '_name', self._name)
            try:
                field.__set__(instance, value)
                matched = True
            except TypeError:
                pass
            except ValueError:
                pass
        if not matched:
            raise ValueError("{}: Did not match any field option".format(self._name))
        super().__set__(instance, value)

    def __str__(self):
        return _str_for_multioption_field(self)


class OneOf(MultiFieldWrapper, Field, metaclass=_JSONSchemaDraft4ReuseMeta):
    """
    Content must adhere to one, and only one, of the requirements in the fields arguments.
    Arguments:

        fields( `list` of :class:`Field`): optional
        the content should match one, and only one, of the fields in the list

    Example:

    .. code-block:: python

        OneOf[Number(maximum=20, minimum=-10), Integer, Positive, String]

    """
    def __init__(self, fields):
        super().__init__(fields=fields)

    def __set__(self, instance, value):
        matched = 0
        for field in self.get_fields():
            setattr(field, '_name', self._name)
            try:
                field.__set__(instance, value)
                matched += 1
            except TypeError:
                pass
            except ValueError:
                pass
        if not matched:
            raise ValueError("{}: Did not match any field option".format(self._name))
        if matched > 1:
            raise ValueError("{}: Matched more than one field option".format(self._name))
        super().__set__(instance, value)

    def __str__(self):
        return _str_for_multioption_field(self)


class NotField(MultiFieldWrapper, Field, metaclass=_JSONSchemaDraft4ReuseMeta):
    """
    Content *must not* adhere to any of the requirements in the fields arguments.
    Arguments:

        fields( `list` of :class:`Field`): optional
            the content must not match any of the fields in the lists

    Examples:

    .. code-block:: python

        NotField([Number(multiplesOf=5, maximum=20, minimum=-10), String])
        NotField[Positive]

    """
    def __init__(self, fields):
        super().__init__(fields=fields)

    def __set__(self, instance, value):
        for field in self.get_fields():
            setattr(field, '_name', self._name)
            try:
                field.__set__(instance, value)
            except TypeError:
                pass
            except ValueError:
                pass
            else:
                raise ValueError("{}: Expected not to match any field definition".
                                 format(self._name))
        super().__set__(instance, value)

    def __str__(self):
        return _str_for_multioption_field(self)


class ValidatedTypedField(TypedField):

    def __set__(self, instance, value):
        self._validate_func(value) # pylint: disable=E1101
        super().__set__(instance, value)


def create_typed_field(classname, cls, validate_func=None):
    """
    Factory that generates a new class for a :class:`Field` as a wrapper of any class.
    Example:
    Given a class Foo, and a validation function for the value in Foo - validate_foo, the line

    .. code-block:: python

        ValidatedFooField = create_typed_field("FooField", Foo, validate_func=validate_foo)

    Generates a new :class:`Field` class that validates the content using validate_foo, and can be
    used just like any :class:`Field` type.

    .. code-block:: python

        class A(Structure):
            foo = ValidatedFooField
            bar = Integer

        # asumming we have an instance of Foo, called my_foo:
        A(bar=4, foo=my_foo)

    Arguments:

        classname(`str`):
            the content must not match any of the fields in the lists
    """
    def validate_wrapper(cls, value):
        if validate_func is None:
            return
        validate_func(value)

    return type(classname, (ValidatedTypedField,), {'_validate_func' :validate_wrapper, '_ty': cls})
