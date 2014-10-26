#!/usr/bin/env python
#
# Copyright 2009 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""pytracker is a Python wrapper around the Tracker API."""

__author__ = 'dcoker@google.com (Doug Coker)'

import calendar
import cookielib
import re
import time
import urllib
import urllib2
import xml.dom
from xml.dom import minidom
import xml.parsers.expat
import xml.sax.saxutils
import json

DEFAULT_BASE_API_URL = 'https://www.pivotaltracker.com/services/v5/'
# Some fields specify UTC, some GMT?
_TRACKER_DATETIME_RE = re.compile(r'^\d{4}/\d{2}/\d{2} .*(GMT|UTC)$')


def TrackerDatetimeToYMD(pdt):
  assert _TRACKER_DATETIME_RE.match(pdt)
  pdt = pdt.split()[0]
  pdt = pdt.replace('/', '-')
  return pdt


class Tracker(object):
  """Tracker API."""

  def __init__(self, project_id, token,
               base_api_url=DEFAULT_BASE_API_URL):
    """Constructor.

    If you are debugging API calls, you may want to use a non-HTTPS API URL:
      base_api_url="http://www.pivotaltracker.com/services/v5/"

    Note that a project owner can prevent non-HTTPS access to a project via API
    versions older than V5. You can check this setting under your project
    settings in the section Access:
      https://www.pivotaltracker.com/projects/PROJECT_ID/settings

    Args:
      project_id: the Tracker ID (integer).
      token: your Pivotal Tracker API token.
      base_api_url: the base URL of the HTTP API (with trailing /).
    """
    self.project_id = project_id
    self.base_api_url = base_api_url

    cookies = cookielib.CookieJar()
    self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookies))

    self.token = token

  def _Api(self, request, method, body=None):
    url = self.base_api_url + 'projects/%d/%s' % (self.project_id,
                                                  request)

    headers = {}
    if self.token:
      headers['X-TrackerToken'] = self.token

    if not body and method == 'GET':
      # Do a GET
      req = urllib2.Request(url, None, headers)
    else:
      headers['Content-Type'] = 'application/xml'
      req = urllib2.Request(url, body, headers)
      req.get_method = lambda: method

    try:
      res = self.opener.open(req)
    except urllib2.HTTPError, e:
      message = "HTTP Status Code: %s\nMessage: %s\nURL: %s\nError: %s" % (e.code, e.msg, e.geturl(), e.read())
      raise TrackerApiException(message)

    return res.read()

  def _ApiQueryStories(self, query=None):
    if query:
      output = self._Api('stories?filter=' + urllib.quote_plus(query),
                         'GET')
    else:
      output = self._Api('stories', 'GET')

    """Confirm data is valid JSON.

    json.loads throws a ValueError if the output is not valid JSON.
    """
    try:
      json.loads(output)
    except ValueError, e:
      message = "JSON was not valid. \nError: %s" % e
      raise TrackerApiException(message)

    return output

  def GetStoriesXml(self):
    return self._ApiQueryStories()

  def GetReleaseStoriesXml(self):
    return self._ApiQueryStories('type:release')

  def GetStories(self, filt=None):
    """Fetch all Stories that satisfy the filter.

    Args:
      filt: a Tracker search filter.
    Returns:
      List of Story().
    """
    data = self._ApiQueryStories(filt)
    stories = json.loads(data)
    lst = []
    for story in stories:
      lst.append(Story.FromJson(story))

    return lst

  def GetStory(self, story_id):
    story_json = self._Api('stories/%d' % story_id, 'GET')
    return Story.FromJson(json.loads(story_json))

  def AddComment(self, story_id, comment):
    comment = '<note><text>%s</text></note>' % xml.sax.saxutils.escape(comment)
    self._Api('stories/%d/notes' % story_id, 'POST', comment)

  def AddNewStory(self, story):
    """Persists a new story to Tracker and returns the new Story."""
    story_xml = story.ToXml()
    res = self._Api('stories', 'POST', story_xml)
    story = Story.FromXml(res)
    return story

  def UpdateStoryById(self, story_id, story):
    """Persist changes to an existing story to Tracker.

    Use this method if you are changing a story without first retreiving the
    story.

    Args:
      story_id: The ID of the story to mutate
      story: The Story containing values to change.
    Returns:
      The updated Story().
    """
    story_xml = story.ToXml()
    res = self._Api('stories/%d' % story_id, 'PUT', story_xml)
    return Story.FromXml(res)

  def UpdateStory(self, story):
    """Persists changes to an existing story to Tracker.

    Use this method if you have a full Story object created by one of the query
    methods.

    Args:
      story: a Story()
    Returns:
      The updated Story().
    """
    story_xml = story.ToXml()
    res = self._Api('stories/%d' % story.GetStoryId(), 'PUT', story_xml)
    return Story.FromXml(res)

  def DeleteStory(self, story_id):
    """Deletes a story by story ID."""
    self._Api('stories/%d' % story_id, 'DELETE', '')


class TrackerApiException(Exception):
  """Raised when Tracker returns an error."""


class Story(object):
  """Represents a Story.

  This class can be used to represent a complete Story (generally queried from
  the Tracker class), or can contain partial information for update or create
  operations (constructed with default constructor).

  Internally, Story uses None to indicate that the client has not specified a
  value for the field or that it has not been parsed from XML.  This enables us
  to use the same Story object to define an update to multiple stories, without
  requiring that the client first fetch, parse, and update an existing story.
  This is supported by all mutable fields except for labels, which are
  represented by Tracker as a comma-separated list of strings in a single tag
  body.  For label operations on existing stories to be performed correctly,
  the Story must first be fetched from the server so that the existing labels
  are not lost.
  """

  # Fields that can be treated as strings when embedding in XML.
  UPDATE_FIELDS = ('story_type', 'current_state', 'name',
                   'description', 'estimate', 'requested_by', 'owned_by')

  # Type: immutable ints.
  story_id = None
  iteration_number = None

  # Type: immutable times (secs since epoch)
  created_at = None

  # Type: mutable time (secs since epoch)
  deadline = None

  # Type: mutable set (API methods expose as string)
  labels = None

  # Type: immutable strings
  url = None

  # Type: mutable strings
  requested_by = None
  owned_by = None
  story_type = None
  current_state = None
  description = None
  name = None
  estimate = None

  def __str__(self):
    return "Story(%r)" % self.__dict__

  @staticmethod
  def FromJson(as_json):
    """Parse a JSON string into a Story.

    Args:
      as_json: a full JSON object from the Tracker API.
    Returns:
      Story()
    """
    story = Story()
    story.story_id = Story._GetDataFromIndex(as_json, 'id')
    story.url = Story._GetDataFromIndex(as_json, 'url')
    story.owned_by = Story._GetDataFromIndex(as_json, 'owner_ids')
    story.requested_by = Story._GetDataFromIndex(as_json, 'requested_by_id')

    iteration = Story._GetDataFromIndex(as_json, 'number')
    if iteration:
      story.iteration_number = int(iteration)

    story.SetStoryType(Story._GetDataFromIndex(as_json, 'story_type'))
    story.SetCurrentState(Story._GetDataFromIndex(as_json, 'current_state'))
    story.SetName(Story._GetDataFromIndex(as_json, 'name'))
    story.SetDescription(Story._GetDataFromIndex(as_json, 'description'))

    created_at = Story._GetDataFromIndex(as_json, 'created_at')
    story.created_at = Story._ParseDatetimeIntoSecs(created_at)

    deadline = Story._GetDataFromIndex(as_json, 'deadline')
    if deadline:
      story.SetDeadline(Story._ParseDatetimeIntoSecs(deadline))

    estimate = Story._GetDataFromIndex(as_json, 'estimate')
    if estimate is not None:
      story.estimate = estimate

    labels = Story._GetDataFromIndex(as_json, 'labels')
    if labels is not None:
      story.AddLabelsFromArray(labels)

    return story

  @staticmethod
  def _GetDataFromIndex(json, index):
    """Retrieve value associated with the index, if any.

    Args:
      json: JSON object
      index: name of the desired index

    Returns:
      None (if index doesn't exist), empty string (if index exists, but value is
      empty), or the index value.
    """
    if not index in json:
      return None
    elif not json[index]:
      return ''
    else:
      return json.get(index)

  @staticmethod
  def _GetDataFromTag(dom, tag):
    """Retrieve value associated with the tag, if any.

    Args:
      dom: XML DOM object
      tag: name of the desired tag

    Returns:
      None (if tag doesn't exist), empty string (if tag exists, but body is
      empty), or the tag body.
    """
    tags = dom.getElementsByTagName(tag)
    if not tags:
      return None
    elif tags[0].hasChildNodes():
      return tags[0].firstChild.data
    else:
      return ''

  @staticmethod
  def _ParseDatetimeIntoSecs(data):
    """Returns the time parsed into seconds-since-epoch."""

    if not data:
      return None
    # Tracker emits datetime strings in UTC or GMT.
    # The [:-4] strips the timezone indicator
    when = time.strptime(data[:-2], '%Y-%m-%dT%H:%M:%S')
    # calendar.timegm treats the tuple as GMT
    return calendar.timegm(when)

  # Immutable fields
  def GetStoryId(self):
    return self.story_id

  def GetIteration(self):
    return self.iteration_number

  def GetUrl(self):
    return self.url

  # Mutable fields
  def GetRequestedBy(self):
    return self.requested_by

  def SetRequestedBy(self, requested_by):
    self.requested_by = requested_by

  def GetOwnedBy(self):
    return self.owned_by

  def SetOwnedBy(self, owned_by):
    self.owned_by = owned_by

  def GetStoryType(self):
    return self.story_type

  def SetStoryType(self, story_type):
    assert story_type in ['bug', 'chore', 'release', 'feature']
    self.story_type = story_type

  def GetCurrentState(self):
    return self.current_state

  def SetCurrentState(self, current_state):
    self.current_state = current_state

  def GetName(self):
    return self.name

  def SetName(self, name):
    self.name = name

  def GetEstimate(self):
    return self.estimate

  def SetEstimate(self, estimate):
    self.estimate = estimate

  def GetDescription(self):
    return self.description

  def SetDescription(self, description):
    self.description = description

  def GetDeadline(self):
    return self.deadline

  def SetDeadline(self, secs_since_epoch):
    self.deadline = secs_since_epoch

  def GetCreatedAt(self):
    return self.created_at

  def SetCreatedAt(self, secs_since_epoch):
    self.created_at = secs_since_epoch

  def AddLabel(self, label):
    """Adds a label (see caveat in class comment)."""
    if self.labels is None:
      self.labels = set()
    self.labels.add(label)

  def RemoveLabel(self, label):
    """Removes a label (see caveat in class comment)."""
    if self.labels is None:
      self.labels = set()
    else:
      try:
        self.labels.remove(label)
      except KeyError:
        pass

  def AddLabelsFromArray(self, labels):
    """Adds a set of labels from a JavaScript array of objects."""
    if self.labels is None:
      self.labels = set()

    self.labels = self.labels.union([x["name"].strip() for x in labels])

  def AddLabelsFromString(self, labels):
    """Adds a set of labels from a comma-delimited string (see class caveat)."""
    if self.labels is None:
      self.labels = set()

    self.labels = self.labels.union([x.strip() for x in labels.split(',')])

  def GetLabelsAsString(self):
    """Returns the labels as a comma delimited list of strings."""
    if self.labels is None:
      return None
    lst = list(self.labels)
    lst.sort()
    return ','.join(lst)

  def ToXml(self):
    """Converts this Story to an XML string."""
    doc = xml.dom.getDOMImplementation().createDocument(None, 'story', None)
    story = doc.getElementsByTagName('story')[0]

    # Most fields are just simple strings or ints, so we treat them all in the
    # same way.
    for field_name in self.UPDATE_FIELDS:
      v = getattr(self, field_name)
      if v is not None:
        new_tag = doc.createElement(field_name)
        new_tag.appendChild(doc.createTextNode(unicode(v)))
        story.appendChild(new_tag)

    # Labels are represented internally as sets.
    if self.labels:
      labels_tag = doc.createElement('labels')
      labels_tag.appendChild(doc.createTextNode(self.GetLabelsAsString()))
      story.appendChild(labels_tag)

    # Dates are special
    DATE_FORMAT = '%Y/%m/%d %H:%M:%S UTC'

    if self.deadline:
      formatted = time.strftime(DATE_FORMAT, time.gmtime(self.deadline))
      deadline_tag = doc.createElement('deadline')
      deadline_tag.setAttribute('type', 'datetime')
      deadline_tag.appendChild(doc.createTextNode(formatted))
      story.appendChild(deadline_tag)

    if self.created_at:
      formatted = time.strftime(DATE_FORMAT, time.gmtime(self.created_at))
      created_at_tag = doc.createElement('created_at')
      created_at_tag.setAttribute('type', 'datetime')
      created_at_tag.appendChild(doc.createTextNode(formatted))
      story.appendChild(created_at_tag)

    return doc.toxml('utf-8')
