"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import copy
import sys
import datetime as dt
from threading import Thread
from time import sleep
import altolib

from typing import Any, List, Mapping, Union, Callable, Optional
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Core
from volttron.platform.scheduling import periodic


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"

SDELIM = "{"
EDELIM = "}"
WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class NOTFORME(Exception):
    """
        An exception used to signal that
        processing was not for oneself.
    """

    pass


class TopicMatch:
    """
    This class handles topic matches
    A topic is defined as a 4-uple
         * schema
         * agent
         * device
         * event

    If one of the element is "", it is considered a parameter and can match any value
    It is expected that the agent 'topic' will also match
    """

    def __init__(self, defs):
        """Create match based on it's definition.. a simple dictionary with one key "topic"
        """

        if "topic" not in defs:
            raise NOTFORME
        try:
            self.schema, self.agent_name, self.device, self.event = defs["topic"]
            _log.debug(
                f"Topic trigger schema {self.schema}, agent {self.agent_name} device {self.device} and evemt {self.event}"
            )
        except:
            _log.debug(f"Topic definition could not be parsed: {defs}")
            raise Exception(f"Topic definition could not be parsed: {defs}")

    def refresh(self, force=False):
        """
             regenerate topic value for comparison.... nothing to do
        """
        pass

    def match(self, topic):
        """ Check if we have a match on topic.

        Return a pair of values:
            A boolean if the topic matches
            The parameter value, a 4-uple of replacement, or None
        """
        _log.debug(
            f"Trying to match {self.schema}/{self.agent_name}/{self.device}/{self.event} to {topic}"
        )
        try:
            schema, agent, device, event = topic
            pvalue = []
            for k, v in [
                ("schema", schema),
                ("agent_name", agent),
                ("device", device),
                ("event", event),
            ]:
                if getattr(self, k):
                    assert getattr(self, k) == v
                pvalue.append(v)

            return True, pvalue
        except:
            return False, None


class TimeMatch:
    """
    This class handles topic matches
    """

    def __init__(self, defs):
        """Create match based on it's definition..
        """
        if "occurrence" not in defs:
            raise NOTFORME
        try:
            self.defs = defs
            self.mytime = None
            self.refresh()
            _log.debug("Time trigger with {}".format(self.mytime))
        except:
            raise Exception("Time definition could not be parsed: {}".format(defs))

    def refresh(self, force=False):
        """
             regenerate mytime value for comparison
        """
        if force:
            self.mytime = None
        now = None
        if self.defs["occurrence"] == "on":
            if not self.mytime:
                now = dt.datetime.now().replace(second=0, microsecond=0)
                now = now.replace(year=self.defs["value"]["year"])
                now = now.replace(month=self.defs["value"]["month"])
                now = now.replace(day=self.defs["value"]["day"])
        elif self.defs["occurrence"] == "every":
            if not self.mytime:
                now = dt.datetime.now().replace(second=0, microsecond=0)
                if self.defs["value"]["repeat"] == "year":
                    now = now.replace(month=self.defs["value"]["month"])
                    now = now.replace(day=self.defs["value"]["day"])
                elif self.defs["value"]["repeat"] == "month":
                    now = now.replace(day=self.defs["value"]["day"])
                elif self.defs["value"]["repeat"] == "day of week":
                    now += dt.timedelta(
                        days=WEEK.index(self.defs["value"]["day of week"])
                        - now.weekday()
                    )
                    if "day" in self.defs["value"]:
                        while self.defs["value"]["day"] != now.day:
                            now += dt.timedelta(days=7)
            elif self.defs["value"]["repeat"] == "hour":
                now = dt.datetime.now().replace(second=0, microsecond=0)

        elif self.defs["occurrence"] == "nth":
            if not self.mytime:
                now = dt.datetime.now().replace(second=0, microsecond=0)
                if self.defs["value"]["repeat"] == "year":
                    if "day" in self.defs["value"]:
                        raise Exception(
                            'Error: Use "every year" for that kind of repetition'
                        )
                    if self.defs["value"]["occur factor"] < 0:
                        search = 1
                        thatday = dt.date(now.year + 1, 1, 1)
                    else:
                        search = -1
                        thatday = dt.date(now.year - 1, 12, 31)
                    if "day of week" in self.defs["value"]:
                        while thatday.weekday() != WEEK.index(
                            self.defs["value"]["day of week"]
                        ):
                            thatday += dt.timedelta(days=search)
                        thatday += dt.timedelta(
                            days=self.defs["value"]["occur factor"] * 7
                        )
                    else:
                        thatday += dt.timedelta(days=self.defs["value"]["occur factor"])
                    now = now.replace(month=thatday.month, day=thatday.day)
                elif self.defs["value"]["repeat"] == "month":
                    if "day" in self.defs["value"]:
                        raise Exception(
                            'Error: Use "every month" for that kind of repetition'
                        )
                    if self.defs["value"]["occur factor"] < 0:
                        search = 1
                        thatday = dt.date(now.year, now.month + 1, 1)
                    else:
                        search = -1
                        thatday = dt.date(now.year, now.month, 1) - dt.timedelta(days=1)
                    if "day of week" in self.defs["value"]:
                        while thatday.weekday() != WEEK.index(
                            self.defs["value"]["day of week"]
                        ):
                            thatday += dt.timedelta(days=search)
                        thatday += dt.timedelta(
                            days=self.defs["value"]["occur factor"] * 7
                        )
                    else:
                        thatday += dt.timedelta(days=self.defs["value"]["occur factor"])
                    now = now.replace(month=thatday.month, day=thatday.day)

        if now:
            if "time" in self.defs["value"]:
                if "hour" in self.defs["value"]["time"]:
                    now = now.replace(hour=self.defs["value"]["time"]["hour"])
                if "minute" in self.defs["value"]["time"]:
                    now = now.replace(minute=self.defs["value"]["time"]["minute"])
                if "ephemeride" in self.defs["value"]:
                    raise Exception("Ephemeride not yet implemented")

            self.mytime = now

    def match(self, topic):
        """ Check if we have a match on time..

        Return a pair of values:
            A boolean if the time matches
            The parameter value or None
        """
        if topic[0] == "timing":
            now = dt.datetime.now().replace(second=0, microsecond=0)
            if self == now:
                return True, None
        return False, None

    def __lt__(self, other):
        return self.mytime < other

    def __le__(self, other):
        return self.mytime <= other

    def __gt__(self, other):
        return self.mytime > other

    def __ge__(self, other):
        return self.mytime >= other

    def __eq__(self, other):
        return self.mytime == other

    def __ne__(self, other):
        return self.mytime >= other


class TimeCondition(TimeMatch):
    """Used for time-based conditions"""

    def __init__(self, defs, vars):
        """This is a simple proxy for TimeMatch"""

        if defs[0] != "timing":
            raise NOTFORME
        thisdef = copy.deepcopy((defs[1]))
        if "day of week" in defs[1]:
            thisdef["repeat"] = "day of week"
        elif "month" in defs[1]:
            thisdef["repeat"] = "year"
        elif "day" in defs[1]:
            thisdef["repeat"] = "month"
        else:
            thisdef["repeat"] = "day"

        mydef = {"occurrence": "every", "value": thisdef}

        super().__init__(mydef)
        self.operator = defs[2]
        if self.operator not in ["==", "!=", "<", "<=", ">", ">="]:
            raise Exception(
                "Unknown time comparison operator: {}".format(self.operator)
            )

    def evaluate(self, val):
        """Evaluate the time condition. val is the payload of the triggering event. Not used here"""
        now = dt.datetime.now().replace(second=0, microsecond=0)
        self.refresh(force=True)
        if self.operator == "==":
            return self == now
        elif self.operator == "!=":
            return self != now
        elif self.operator == "<":
            return self > now
        elif self.operator == "<=":
            return self <= now
        elif self.operator == ">":
            return self < now
        elif self.operator == ">=":
            return self <= now
        return False


class EventCondition:
    """ Condition checking the value associated with the trigger payload. """

    def __init__(self, defs, vars):
        if defs[0] != "event":
            raise NOTFORME
        # if not defs[1]:
        # raise Exception("Nothing to compare")
        self.keys = defs[1].split("::")
        self.operator, self.cmpval = defs[2]
        self.vars = vars
        _log.debug(
            "Got an event condition with {} {} {}".format(
                self.keys, self.operator, self.cmpval
            )
        )
        if self.operator not in ["==", "!=", "<", "<=", ">", ">=", "in", "not in"]:
            raise Exception("Unknown comparison operator: {}".format(self.operator))

    def evaluate(self, val):
        """Evaluate the event condition. val is the payload of the triggering event"""
        # Grab the value
        _log.debug(
            f"Evaluating event condition: {self.keys},{self.operator},{self.cmpval}"
        )
        try:
            cmpval = val
            for k in self.keys:
                # _log.debug("Checking for key {}  in {}".format(k, cmpval))
                cmpval = cmpval[k]
        except:
            _log.warning(
                "Error retrieving value {} in {}. Assuning False".format(self.keys, val)
            )
            return False

        # _log.debug("Checking if {} {} {}".format(cmpval, self.operator, self.cmpval))

        try:
            if isinstance(self.cmpval, str) and self.cmpval.startswith("__var__"):
                myval = self.vars[self.cmpval.replace("__var__", "")]
            else:
                myval = self.cmpval
            if self.operator == "==":
                return cmpval == myval
            elif self.operator == "!=":
                return cmpval != myval
            elif self.operator == "<":
                return cmpval < myval
            elif self.operator == "<":
                return cmpval < myval
            elif self.operator == ">":
                return cmpval > myval
            elif self.operator == ">=":
                return cmpval >= myval
            elif self.operator == "in":
                return cmpval in myval
            elif self.operator == "not in":
                return cmpval not in myval
            return False
        except:
            _log.warning(
                "Values {} vs {} and operator {} do not match. Assuning False".format(
                    self.cmpval, cmpval, self.operator
                )
            )


class VariableCondition:
    """ Condition checking the current value of  a state varieble. """

    def __init__(self, defs, vars):
        if defs[0] != "variable":
            raise NOTFORME
        if not defs[1]:
            raise Exception("Nothing to compare")
        self.name = defs[1]
        self.vars = vars
        self.operator, self.cmpval = defs[2]
        _log.debug(
            "Got an variablke condition with {} {} {}".format(
                self.name, self.operator, self.cmpval
            )
        )
        if self.operator not in ["==", "!=", "<", "<=", ">", ">=", "in", "not in"]:
            raise Exception("Unknown comparison operator: {}".format(self.operator))

    def evaluate(self, val):
        """Evaluate the event condition. val is the payload of the triggering event"""
        # Grab the value

        cmpval = self.vars[self.name]

        # _log.debug("Checking if {} {} {}".format(cmpval, self.operator, self.cmpval))

        try:
            if isinstance(self.cmpval, str) and self.cmpval.startswith("__var__"):
                myval = self.vars[self.cmpval.replace("__var__", "")]
            else:
                myval = self.cmpval
            if self.operator == "==":
                return cmpval == myval
            elif self.operator == "!=":
                return cmpval != myval
            elif self.operator == "<":
                return cmpval < myval
            elif self.operator == "<":
                return cmpval < myval
            elif self.operator == ">":
                return cmpval > myval
            elif self.operator == ">=":
                return cmpval >= myval
            elif self.operator == "in":
                return cmpval in myval
            elif self.operator == "not in":
                return cmpval not in myval
            return False
        except:
            _log.warning(
                "Values {} vs {} and operator {} do not match. Assuning False".format(
                    self.cmpval, cmpval, self.operator
                )
            )


def action(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Action
    :rtype: Action
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    topic = config.get("topic", "")
    kwargs["agent_name"] = config.get("agent_name", "action")
    kwargs["devid"] = config.get("devid", "action")
    kwargs["location"] = config.get(
        "location", ["13.7500 N", "100.5167 E"]
    )  # Default to Bangkok
    kwargs["rules"] = config.get("rules", {})
    kwargs["state_variables"] = config.get("state_variables", {})

    return Action(topic, **kwargs)


class Action(altolib.AltoAgent):
    """
    Document agent constructor here.
    """

    def __init__(self, topic: str = "", **kwargs: int) -> altolib.AltoAgent:
        super().__init__(topic, **kwargs)
        self._loattr.add("rules")
        self._attrtypes["rules"] = dict
        self._loattr.add("location")
        self._attrtypes["location"] = list
        self._loattr.add("state_variables")
        self._attrtypes["state_variables"] = dict
        self._loattr.add("devid")
        self.schemas.add("actions")
        self.compiled_rules = {}
        self.threads = []
        self.device_list = {self.devid: None}
        self.last_tick = None
        self.do_save = False

    def configure(
        self, config_name: str, action: str, contents: Mapping[str, Any]
    ) -> None:

        oldrules = copy.deepcopy(self.rules)
        super().configure(config_name, action, contents)
        self.device_list = {self.devid: None}
        if self.rules != oldrules:
            self._compile_rules()
        else:
            _log.debug("Did not compile")

    def _compile_rules(self):
        """
        Here we compile the rules

        """

        try:
            oldrules = copy.deepcopy(self.compiled_rules)
            self.compiled_rules = {}
            # Let's compile the rules
            for name, rule in self.rules.items():
                mytrig = None
                clist = []
                myactions = []
                for cl in [TopicMatch, TimeMatch]:
                    mytrig = None
                    try:
                        mytrig = cl(rule["trigger"])
                    except NOTFORME:
                        continue
                    except Exception as e:
                        _log.warning(
                            "Error with trigger for rule {}: {}".format(name, e)
                        )
                        mytrig = None
                    break
                for cnd in rule["conditions"]:
                    try:
                        thiscond = None
                        for cl in [EventCondition, TimeCondition, VariableCondition]:
                            try:
                                thiscond = cl(cnd, self.state_variables)
                            except NOTFORME:
                                continue
                            clist.append(thiscond)
                    except Exception as e:
                        _log.warning(
                            "Error with condition for rule {}: {}".format(name, e)
                        )
                        clist = None
                        break
                _log.debug("About to write the rule: {} {}".format(mytrig, clist))
                if mytrig and rule["actions"] and not clist is None:
                    self.compiled_rules[name] = {
                        "trigger": mytrig,
                        "conditions": clist,
                        "actions": rule["actions"],
                    }
                else:
                    _log.warning(
                        "Error: Rule {} cannot be compiled. Ignoring.".format(name)
                    )

            self.set_heartbeat_status("GOOD")
        except Exception as e:
            _log.error(f"Rules could not be parsed. Rules are unchanged")
            _log.debug(f"Error was {e}")
            self.compiled_rules = oldrules

    def _create_subscriptions(self):
        # Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(
            peer="pubsub", prefix=self.topic, callback=self._handle_message
        )

    def _handle_message(self, peer, sender, bus, topic, headers, message):
        """
        Here we handle as much as the message as we can. For any agent, the subclass can define a method
        following the format

                handle_<type>_<schema>

        For instance, 'handle_event_sensor', handle_response_switch',

        Those method require 2 parametres (3 for responses):
               The end of topic, that is the topic minus prefix, schema and agent.
               The payload from the message
               The headers, for responses only.

        """
        if sender != self.core.identity:  # Let's not bother with our own messages
            try:
                split_topic = topic.replace(self.topic, "").split("/")
                _log.debug(f"Split topic is {split_topic}")
                schema = split_topic[0]
                name = split_topic[1]
                mtype = headers["message_type"].lower().strip()
                _log.debug(f"Executing handle_{mtype}_{schema} ")
                if mtype == "response":
                    getattr(self, "handle_" + mtype + "_" + schema)(
                        split_topic[2:], message, headers
                    )
                elif mtype == "event":
                    self.handle_events(split_topic, message, headers)
                else:
                    assert name == self.agent_name
                    getattr(self, "handle_" + mtype + "_" + schema)(
                        split_topic[2:], message
                    )
            except Exception as e:
                pass
                # _log.debug(
                # f"Problem handling message from {sender}. \n\tHeader: {headers}, \n\ttopic: {topic}, \n\tmessage: {message},\n\terror: {e}"
                # )
                # _log.exception((e))

    def handle_events(self, topic, message, headers):
        """
        Special handling here since we want to catch all events
        """
        try:
            schema, agent, device, func = topic
        except:
            # _log.debug(
            # f"Got a message with a topic that does not have 4 elements. Got {topic}"
            # )
            return

        # Let's process the rules
        lorules = [x for x in self.compiled_rules.keys()]
        lorules.sort()
        for name in lorules:
            try:
                # _log.debug("Checking Trigger for rule {}".format(name))
                trigger, param = self.compiled_rules[name]["trigger"].match(topic)
                if trigger:
                    _log.debug("Trigger matches for rule {}".format(name))
                    cond = True
                    for acond in self.compiled_rules[name]["conditions"]:
                        _log.debug("Checking condition for rule {}".format(name))
                        if not acond.evaluate(message):
                            cond = False
                            break
                    if cond:
                        _log.debug("Rule {} will be executed".format(name))
                        self._execute(name, param, message)
            except Exception as e:
                _log.error(f"Could not execute rule {name}")
                _log.debug(f"Exception was {e}")
                _log.exception(e)

    def handle_request_action(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:

        """
        Handling add_device, del_device and map for the location.

        """

        _log.debug(f"Action request from {topic}")
        if len(topic) == 2:
            devid, func = topic
            assert devid in self.device_list
        else:
            func = topic[0]
            devid = None
        _log.debug(f"Request with {func}")
        rmsg = None
        if func == "list_rules":
            _log.debug(f"list of rules as {self.rules.__class__}")
            rmsg = {"rid": message["rid"]}
            rmsg["rules"] = self.rules
        elif func == "list_variables":
            rmsg = {"rid": message["rid"]}
            rmsg["variables"] = self.state_variables
        elif func == "reset_variables":
            rmsg = {"rid": message["rid"]}
            if "variables" not in message or not message["variables"]:
                check = lambda x: True
            else:
                check = lambda x: x in message["variables"]
            for k in self.state_variables:
                if check(k):
                    self.state_variables[k] = self.state_variables[k].__class__()
            rmsg["reset"] = True
            self.do_save = True
        if rmsg:
            self.publish(message["reply_to"], rmsg, "response")

    def handle_request_config(
        self, topic: List[str], message: Mapping[str, Any]
    ) -> None:

        """
        Handling add_device, del_device and map for the location.

        """

        _log.debug(f"Action Configuring from {topic}")
        if len(topic) == 2:
            devid, func = topic
            assert devid in self.device_list
        else:
            func = topic[0]
            devid = None
        _log.debug(f"Configuring with {func}")
        if func == "add_rules":
            dosave = False
            notsaved = []
            for rule_name in message["rules"]:
                if rule_name not in self.rules:
                    self.rules[rule_name] = message["rules"][rule_name]
                    dosave = True
                else:
                    notsaved.append(rule_name)
            rmsg = {"rid": message["rid"]}
            if dosave:
                if notsaved:
                    rmsg["save"] = "partial"
                    rmsg[
                        "error_msg"
                    ] = "Not all rules could be saved. Some name already exist?"
                    rmsg["error_list"] = notsaved
                else:
                    rmsg["save"] = True
                self.save_config()
                self._compile_rules()
            else:
                rmsg["save"] = False
                rmsg["error_msg"] = "No rule could be saved. Some name already exist?"
            self.publish(message["reply_to"], rmsg, "response")

        elif func == "del_rules":
            dosave = False
            notsaved = []
            for rule_name in message["rules"]:
                if rule_name not in self.rules:
                    notsaved.append(rule_name)
                else:
                    del self.rules[rule_name]
                    dosave = True
            rmsg = {"rid": message["rid"]}
            if dosave:
                if notsaved:
                    rmsg["save"] = "partial"
                    rmsg[
                        "error_msg"
                    ] = "Not all rules could be deleted. Some name do not exist?"
                    rmsg["error_list"] = notsaved
                else:
                    rmsg["save"] = True
                self.save_config()
                self._compile_rules()
            else:
                rmsg["save"] = False
                rmsg["error_msg"] = "No rule could be deleted. Names do not exist?"
            self.publish(message["reply_to"], rmsg, "response")

        elif func == "add_variables":
            dosave = False
            notsaved = []
            for var_name in message["variables"]:
                if var_name not in self.state_variables and message["variables"][
                    var_name
                ].__class__ in [int, float, str, list]:
                    self.state_variables[var_name] = message["variables"][var_name]
                    dosave = True
                else:
                    notsaved.append(var_name)
            rmsg = {"rid": message["rid"]}
            if dosave:
                if notsaved:
                    rmsg["save"] = "partial"
                    rmsg[
                        "error_msg"
                    ] = "Not all variables could be saved. Some name may already exist? Was the value a numeral, a string or a list?"
                    rmsg["error_list"] = notsaved
                else:
                    rmsg["save"] = True
                self.save_config()
            else:
                rmsg["save"] = False
                rmsg[
                    "error_msg"
                ] = "No variable could be saved. Some name already exis? Was the value a numeral, a string or a list?"
            self.publish(message["reply_to"], rmsg, "response")

        elif func == "del_variables":
            dosave = False
            notsaved = []
            for var_name in message["variables"]:
                if var_name not in self.state_variables:
                    notsaved.append(var_name)
                else:
                    del self.state_variables[var_name]
                    dosave = True
            rmsg = {"rid": message["rid"]}
            if dosave:
                if notsaved:
                    rmsg["save"] = "partial"
                    rmsg[
                        "error_msg"
                    ] = "Not all variables could be deleted. Some name do not exist?"
                    rmsg["error_list"] = notsaved
                else:
                    rmsg["save"] = True
                self.save_config()
            else:
                rmsg["save"] = False
                rmsg["error_msg"] = "No variable could be deleted. Names do not exist?"
            self.publish(message["reply_to"], rmsg, "response")

    @Core.schedule(periodic(5))
    def timing_event(self):
        # Update if needed
        now = dt.datetime.now().replace(second=0, microsecond=0)
        if now == self.last_tick:
            return
        self.last_tick = now
        if now.minute == 0:
            if now.hour == 0:
                force = True
            else:
                force = False
            lorules = [x for x in self.rules.keys()]
            lorules.sort()
            for name in lorules:
                self.compiled_rules[name]["trigger"].refresh(force)

        self.handle_events(["timing", "", "", ""], None, None)

    @Core.schedule(periodic(180))
    def clean_threads(self):
        # Update if needed
        _log.debug(f"Cleaning up to {len(self.threads)}")
        to = dt.datetime.now() - dt.timedelta(minutes=10)
        idxtodel = []
        idx = 0
        for x, t in self.threads:
            if not x.is_alive():
                idxtodel.append(idx)
            if t < to:
                _log.warning(
                    f"Thread {x.name} has been running for more than 10 minutes"
                )
        for idx in idxtodel[::-1]:
            del self.threads[idx]
        _log.debug(f"{len(self.threads)} threads remaining.")

    @Core.schedule(periodic(120))
    def saving_variables(self):
        if self.do_save:
            self.do_save = False
            self.save_config()

    def _execute(self, name, param, payload):
        """
        This method will start a thread to execute a rule that was triggered
        and for which no condition evaluated False.
        """

        _log.debug("Starting rule execution")
        thread = Thread(
            target=self._execute_one, args=(self.rules[name]["actions"], param, payload)
        )
        thread.setDaemon(True)
        thread.name = name
        thread.start()
        self.threads.append([thread, dt.datetime.now()])

    def _execute_one(self, actions, param, payload):
        """ Execute one list of rules. This happens in a thread."""
        for topic, cvalue in actions:
            _log.debug(f"Starting with {topic} and {cvalue}")
            try:
                if param is None:
                    # A timing  trigger
                    param = ["", "", "", ""]

                # Let's start by substituting values in the action payload
                value = copy.deepcopy(cvalue)
                trigtopic = {
                    x: y
                    for (x, y) in zip(["schema", "agent", "device", "event"], param)
                }
                if isinstance(value, dict):
                    for k, v in value.items():
                        if isinstance(v, str) and v.startswith("__var__"):
                            value[k] = self.state_variables[v.replace("__var__", "")]
                        elif isinstance(v, str) and v.startswith("__topic__"):
                            value[k] = trigtopic[v.replace("__topic__", "")]
                        elif isinstance(v, str) and v.startswith("__event__"):
                            keys = v.replace("__event__", "").split("::")
                            plval = payload
                            for pk in keys:
                                _log.debug(
                                    f"Exec topic payload for key {k}  in {plval}"
                                )
                                plval = plval[pk]
                            value[k] = plval
                elif isinstance(value, str) and value.startswith("__var__"):
                    value = self.state_variables[value.replace("__var__", "")]
                elif isinstance(value, str) and value.startswith("__topic__"):
                    value = trigtopic[value.replace("__topic__", "")]
                elif isinstance(value, str) and value.startswith("__event__"):
                    keys = v.replace("__event__", "").split("::")
                    value = payload
                    for pk in keys:
                        _log.debug(f"Exec scalar topic payload for key {k}  in {value}")
                        value = value[pk]
            except Exception as e:
                _log.error(
                    f"Could not perform payload substitution for {topic} and {cvalue}"
                )
                _log.debug(f"Error was {e}")
                _log.exception(e)
                return

            _log.debug(f"Now with {topic} and {value}")
            if topic == "sleep":
                sleep(value)
            elif topic == "variable_set":
                for k, v in value.items():
                    if k in self.state_variables:
                        if k.startswith("__str__"):
                            self.state_variables[k] = str(v)
                            _log.debug(f"Set state variable {k} to str({v})")
                        else:
                            self.state_variables[k] = v
                            _log.debug(f"Set state variable {k} to {v}")
                    self.do_save = True

            elif topic == "variable_add":
                try:
                    for k, v in value.items():
                        if k in self.state_variables:
                            if isinstance(self.state_variables[k], list):
                                if v not in self.state_variables[k]:
                                    self.state_variables[k].append(v)
                            else:
                                self.state_variables[k] += v
                            _log.debug(f"Added {v} to state variable {k} ")
                    self.do_save = True
                except Exception as e:
                    _log.error(f"Cannot 'variable_add' {v} to variable {k}")
                    _log.exception(e)
                    return
            elif topic == "variable_del":
                try:
                    for k, v in value.items():
                        if k in self.state_variables:
                            if isinstance(self.state_variables[k], list):
                                if v in self.state_variables[k]:
                                    self.state_variables[k].remove(v)
                            elif isinstance(self.state_variables[k], str):
                                self.state_variables[k].replace(v, "")
                            else:
                                self.state_variables[k] -= v
                            _log.debug(f"Added {v} to state variable {k} ")
                    self.do_save = True
                except Exception as e:
                    _log.error(f"Cannot 'variable_add' {v} to variable {k}")
                    _log.exception(e)
                    return
            elif topic == "variable_wait":
                try:
                    vn, val, to = value
                    to = 0 - to
                    was_met = False
                    while to != 0:
                        if self.state_variables[vn] == val:
                            was_met = True
                            break
                        to += 1
                        sleep(1)
                    if not was_met:
                        _log.warning("Rule's variable_wait timed out. Aborting")
                        return
                except Exception as e:
                    _log.error(
                        f"Cannot 'variable_wait' {v} to {self.state_variables[k]}"
                    )
                    _log.exception(e)
                    return

            else:
                ctopic = []
                try:
                    thisaction = "command"
                    if len(topic) == 4:
                        ctopic = [self.topic] + topic
                    elif topic[0] == "event" and len(topic) == 5:
                        ctopic = [self.topic] + topic[1:]
                        thisaction = "event"
                    elif topic[0] == "event" and len(topic) > 5:
                        ctopic = topic[1:]
                        thisaction = "event"
                    else:
                        ctopic = topic
                    # Substitution in action topic from event topic
                    ctopic = [x or y for (x, y) in zip(ctopic, [self.topic] + param)]
                    # Clean up empty strings
                    while ctopic[0] == "":
                        ctopic = ctopic[1:]
                    # Create topic string
                    stopic = "/".join(ctopic)
                    #if len(ctopic) == 4 and self.topic:
                        #stopic = self.topic + "/" + stopic

                    self.publish(stopic, value, thisaction)
                except Exception as e:
                    _log.error(
                        f"Action {topic} with value {value} to {ctopic} could not be executed."
                    )
                    _log.debug(f"Error was {e}")
                    _log.exception(e)

    def register_self(self):
        """
        Needs to be defined for non-bridge agents

        """
        pass

    def last_rites(self):
        """
        Check if there are things to save.... if so do it.
        """

        if self.do_save:
            self.save_config()


def main():
    """Main method called to start the agent."""
    utils.vip_main(action, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
