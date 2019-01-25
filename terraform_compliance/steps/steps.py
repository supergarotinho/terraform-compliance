# -*- coding: utf-8 -*-

from radish import step, world, custom_type, given, when, then
from terraform_compliance.steps import resource_name, encryption_property
from terraform_compliance.common.helper import check_sg_rules
from terraform_compliance.common.pyhcl_helper import parse_hcl_value
from terraform_compliance.extensions.terraform_validate import normalise_tag_values
from terraform_validate.terraform_validate import TerraformPropertyList, TerraformResourceList
from terraform_compliance.extensions.ext_radish_bdd import skip_step, step_condition, write_stdout
import re

# world.config.debug_steps = True

# New Arguments
@custom_type("ANY", r"[\.\/_\-A-Za-z0-9\s]+")
def custom_type_any(text):
    return text

@custom_type("SECTION", r"[a-z]+")
def custom_type_section(text):
    if text in ['resource', 'provider', 'data', 'module', 'output', 'terraform', 'variable']:
        return text

@given(u'I have {name:ANY} {type:SECTION} configured')
def i_have_name_section_configured(step, name, type, radish_world=None):
    if radish_world is None:
        radish_world = world

    step.context.type = type
    step.context.name = name

    if type == "resource":
        if (name in resource_name.keys()):
            name = resource_name[name]

        found_resource = radish_world.config.terraform.resources(name)

        if hasattr(found_resource, 'resource_list') and found_resource.resource_list:
            step.context.resource_type = name
            step.context.defined_resource = name
            step.context.stash = radish_world.config.terraform.resources(name)
        else:
            skip_step(step, name)
    else:
        if type in radish_world.config.terraform.terraform_config:
            if name in radish_world.config.terraform.terraform_config[type]:
                step.context.stash = radish_world.config.terraform.terraform_config[type][name]
            else:
                step.context.stash = radish_world.config.terraform.terraform_config[type]

        else:
            skip_step(step, type)

@given(u'I have {resource:ANY} defined')
def i_have_resource_defined(step, resource, radish_world=None):
    if radish_world is None:
        radish_world = world

    if (resource in resource_name.keys()):
        resource = resource_name[resource]

    found_resource = radish_world.config.terraform.resources(resource)

    if found_resource.resource_list:
        step.context.resource_type = resource
        step.context.defined_resource = resource
        step.context.stash = radish_world.config.terraform.resources(resource)
    else:
        skip_step(step, '{} resource'.format(resource))

@when(u'I {action_type:ANY} them')
def i_action_them(step, action_type):
    if action_type == "count":
        step.context.stash = len(step.context.stash.resource_list)
    elif action_type == "sum":
        step.context.stash = sum(step.context.stash.resource_list)
    else:
        AssertionError("Invalid action_type in the scenario: {}".format(action_type))


@then(u'I expect the result is {operator:ANY} than {number:d}')
def i_expect_the_result_is_operator_than_number(step, operator, number):
    value = int(step.context.stash)

    if operator == "more":
        assert value > number, "{} is not more than {}".format(value, number)
    elif operator == "more and equal":
        assert value >= number, "{} is not more and equal than {}".format(value, number)
    elif operator == "less":
        assert value < number, "{} is not less than {}".format(value, number)
    elif operator == "less and equal":
        assert value <= number, "{} is not less and equal than {}".format(value, number)
    else:
        AssertionError('Invalid operator: {}'.format(operator))

@when(u'it contain {something:ANY}')
@when(u'it contains {something:ANY}')
@then(u'it must contain {something:ANY}')
def it_condition_contain_something(step, something,
                                   propertylist=TerraformPropertyList, resourcelist=TerraformResourceList):

    if something in resource_name.keys():
        something = resource_name[something]

    step_can_skip = step_condition(step) in ["given", "when"]

    if step.context.stash.__class__ is propertylist:
        for property in step.context.stash.properties:
            value = parse_hcl_value(property.property_value, world.config.terraform.terraform_config)

            if value is not None:
                assert (value == something or something.lower() in value), \
                    '{} property in {} can not be found in {} ({}). It is set to {} instead'.format(something,
                                                                                                    property.property_name,
                                                                                                    property.resource_name,
                                                                                                    property.resource_type,
                                                                                                    value)
            else:
                write_stdout(level='WARNING',
                             message='Can not get value of {} in {}/{}. '
                                     'Might be set by an unknown source (module, etc. )\n'
                                     'Value : {}'.format(something,
                                                             property.property_name,
                                                             property.resource_type,
                                                             property.property_value))
                step.state = 'skipped'

    elif step.context.stash.__class__ is resourcelist:
        if step_can_skip is False:
            step.context.stash.should_have_properties(something)
            step.context.stash = step.context.stash.find_property(something)
            assert step.context.stash.properties, \
                'No defined property/value found for {}.'.format(something)
            step.context.stash = step.context.stash.properties
        else:
            try:
                step.context.stash.should_have_properties(something)
                number_of_resources = len(step.context.stash.resource_list)
                step.context.stash = step.context.stash.find_property(something)
                if step.context.stash:
                    if number_of_resources > len(step.context.stash.properties):
                        write_stdout(level='INFO',
                                     message='Some of the resources does not have {} property defined within.\n'
                                             'Removed {} resource (out of {}) from the test scope.\n\n'.format(something,
                                                                    (number_of_resources-len(step.context.stash.properties)),
                                                                                                               number_of_resources,
                                                                    ))
            except Exception as e:
                number_of_resources = len(step.context.stash.resource_list)
                step.context.stash = step.context.stash.find_property(something)
                if step.context.stash:
                    write_stdout(level='INFO',
                                 message='Some of the resources does not have {} property defined within.\n' 
                                         'Removed {} resource (out of {}) from the test scope.\n\n'
                                         'Due to : \n{}'.format(something,
                                                    (number_of_resources-len(step.context.stash.properties)),
                                                                number_of_resources,
                                                    str(e)))
                else:
                    skip_step(step,
                              resource=something,
                              message='Can not find {resource} property in any resource.')

    elif step.context.stash.__class__ is dict:
        if something in step.context.stash:
            step.context.stash = step.context.stash[something]
        else:
            if step_can_skip:
                skip_step(step,
                          resource=something,
                          message='Can not find {resource} resource in terraform files.')
            else:
                assert False, '{} does not exist.'.format(something)


@when(u'its {property:ANY} contain {key:ANY}')
@when(u'its {property:ANY} contains {key:ANY}')
def its_property_contains_key(step, property, key, resourcelist=TerraformResourceList):
    if step.context.stash.__class__ is resourcelist:
        number_of_resources = len(step.context.stash.resource_list)
        step.context.stash = step.context.stash.find_property(property).find_property(key)
        if step.context.stash:
            if len(step.context.stash.properties) > 0:
                if number_of_resources > len(step.context.stash.properties):
                    write_stdout(level='INFO',
                                 message='Some of the resources does not have {} property defined within.\n'
                                         'Removed {} resource (out of {}) from the test scope.\n\n'.format(property,
                                                                                                           (
                                                                                                            number_of_resources -
                                                                                                            len(step.context.stash.properties)),
                                                                                                           number_of_resources,
                                                                                                           ))
            else:
                skip_step(step, resource=str(property) + " with key " + str(key),
                          message='Can not find {resource} property in any resource.')
        else:
            skip_step(step, resource=str(property) + " with key " + str(key),
                      message='Can not find {resource} property in any resource.')
    else:
        skip_step(step)

@then(u'encryption is enabled')
@then(u'encryption must be enabled')
def encryption_is_enabled(step):
    prop = encryption_property[step.context.resource_type]
    step.context.stash.property(prop).should_equal(True)


@then(u'its value {condition} match the "{search_regex}" regex')
def its_value_condition_match_the_search_regex_regex(step, condition, search_regex):
    regex = r'{}'.format(search_regex)

    if step.context.stash.__class__ in (str, unicode):
        matches = re.match(regex, step.context.stash)

        if condition == 'must':
            assert matches is not None, \
                '{} {} tests failed on {} regex: {}'.format(step.context.name,
                                                            step.context.type,
                                                            regex,
                                                            step.context.stash)
        elif condition == "must not":
            assert matches is None, \
                '{} {} tests failed on {} regex: {}'.format(step.context.name,
                                                            step.context.type,
                                                            regex,
                                                            step.context.stash)
    else:
        normalise_tag_values(step.context.stash)


        for property in step.context.stash.properties:
            if type(property.property_value) in [str, unicode]:
                property.property_value = [property.property_value]
            elif type(property.property_value) is dict:
                property.property_value = property.property_value.values()

            for value in property.property_value:
                matches = re.match(regex, value)

                if condition == 'must':
                    assert matches is not None, \
                        '{} property in {} does not match with {} regex. It is set to {} instead.'.format(property.property_name,
                                                                                                      property.resource_name,
                                                                                                      search_regex,
                                                                                                      value)
                elif condition == 'must not':
                    assert matches is not None, \
                        '{} property in {} does not match with {} regex. It is set to {} instead.'.format(property.property_name,
                                                                                                          property.resource_name,
                                                                                                          search_regex,
                                                                                                          value)

@step(u'its value must be set by a variable')
def its_value_must_be_set_by_a_variable(step):
    step.context.stash.property(step.context.search_value).should_match_regex(r'\${var.(.*)}')


@then(u'it must not have {proto} protocol and port {port:d} for {cidr:ANY}')
def it_must_not_have_proto_protocol_and_port_port_for_cidr(step, proto, port, cidr):
    proto = str(proto)
    port = int(port)
    cidr = str(cidr)

    for item in step.context.stash.properties:
        if type(item.property_value) is list:
            for security_group in item.property_value:
                check_sg_rules(world.config.terraform.terraform_config, security_group, proto, port, cidr)
        else:
            check_sg_rules(world.config.terraform.terraform_config, item.property_value, proto, port, cidr)