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
__maintainer__ = 'michaelwnelson (Michael Nelson)'

import calendar
import cookielib
import re
import time
import urllib
import urllib2
import json

DEFAULT_BASE_API_URL = 'https://www.pivotaltracker.com/services/v5/'

def GetDataFromIndex(data, index):
  """Retrieve value associated with the index, if any.

  Args:
    data: JSON object
    index: name of the desired index

  Returns:
    None (if index doesn't exist), empty string (if index exists, but value is
    empty), or the index value.
  """
  if not index in data:
    return None
  elif not data[index]:
    return ''
  else:
    return data.get(index)

class Tracker(object):
  """Tracker API."""

  def __init__(self, project_id, token, base_api_url=DEFAULT_BASE_API_URL):
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

  def _ValidateJson(self, data):
    """Confirm data is valid JSON.
      json.loads throws a ValueError if the output is not valid JSON.
    """
    try:
      json.loads(data)
      return True
    except ValueError, e:
      message = "JSON was not valid. \nError: %s" % e
      raise TrackerApiException(message)
      return False

  def _Api(self, request, method, body=None):
    url = self.base_api_url + 'projects/%d/%s' % (self.project_id, request)

    headers = {}
    if self.token:
      headers['X-TrackerToken'] = self.token

    if not body and method == 'GET':
      req = urllib2.Request(url, None, headers)
    else:
      headers['Content-Type'] = 'application/json'
      req = urllib2.Request(url, body, headers)
      req.get_method = lambda: method

    try:
      res = self.opener.open(req)
    except urllib2.HTTPError, e:
      message = "HTTP Status Code: %s\nMessage: %s\nURL: %s\nError: %s" % (
        e.code, e.msg, e.geturl(), e.read())
      raise TrackerApiException(message)

    return res.read()

  def _ApiQueryStories(self, query=None):
    if query:
      output = self._Api('stories?fields=:default,requested_by&filter='
                + urllib.quote_plus(query), 'GET')
    else:
      output = self._Api('stories?fields=:default,requested_by', 'GET')

    if(self._ValidateJson(output)):
      return output

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
    data = self._ApiQueryStories('id:%d' % story_id)
    story = json.loads(data)
    return Story.FromJson(story[0])

  def AddComment(self, story_id, comment):
    comment = json.dumps({'text':comment})
    self._Api('stories/%d/comments' % int(story_id), 'POST', comment)

  def DeleteStory(self, story_id):
    """Deletes a story by story ID."""
    self._Api('stories/%d' % story_id, 'DELETE', '')


class TrackerApiException(Exception):
  """Raised when Tracker returns an error."""


class Story():
  """Represents a Story.

  This class can be used to represent a complete Story (generally queried from
  the Tracker class), or can contain partial information for update or create
  operations.

  Internally, Story uses None to indicate that the client has not specified a
  value for the field or that it has not been parsed from JSON.  This enables us
  to use the same Story object to define an update to multiple stories, without
  requiring that the client first fetch, parse, and update an existing story.
  """

  def __init__(self, data):
    """Initialize Story attributes."""

    attributes = ['id', 'project_id', 'name', 'description', 'story_type',
      'current_state', 'estimate', 'accepted_at', 'deadline', 'requested_by_id',
      'requested_by_kind', 'requested_by_name', 'requested_by_email',
      'requested_by_initials', 'requested_by_username', 'owner_ids', 'labels',
      'created_at', 'updated_at', 'url', 'kind', 'iteration']

    for attr in attributes:
      setattr(self, attr, GetDataFromIndex(data, attr))

    #
    # Special handling for requested_by because by default Pivotal Tracker only
    # provides the the ID of the person, and we want their name, email, etc.
    #
    # This is why we override all requests (re: _ApiQueryStories):
    # ?fields=:default,requested_by
    #
    # Otherwise, we'd have to send another request to the /membership endpoint
    # to then parse and find the person.
    # Let's put that processing on Pivotal Tracker's servers ;)
    #
    requested_by = GetDataFromIndex(data, 'requested_by')
    self.requested_by_id = GetDataFromIndex(requested_by, 'id')
    self.requested_by_kind = GetDataFromIndex(requested_by, 'kind')
    self.requested_by_name = GetDataFromIndex(requested_by, 'name')
    self.requested_by_email = GetDataFromIndex(requested_by, 'email')
    self.requested_by_initials = GetDataFromIndex(requested_by, 'initials')
    self.requested_by_username = GetDataFromIndex(requested_by, 'username')

    # Special handling for created_at to parse datetime
    created_at = GetDataFromIndex(data, 'created_at')
    self.created_at = Story.ParseDatetimeIntoSecs(self, created_at)

    # Special handling for deadline to parse datetime
    deadline = GetDataFromIndex(data, 'deadline')
    if deadline:
      self.SetDeadline(Story.ParseDatetimeIntoSecs(self, deadline))

    # Special handling for labels, we just want the "name"
    labels = GetDataFromIndex(data, 'labels')
    if labels is not None:
      self.AddLabelsFromArray(labels)

  def __str__(self):
    return "Story(%r)" % self.__dict__

  def ParseDatetimeIntoSecs(self, data):
    """Returns the time parsed into seconds-since-epoch."""

    if not data:
      return None
    # Tracker emits datetime strings in UTC or GMT.
    # The [:-4] strips the timezone indicator
    when = time.strptime(data[:-2], '%Y-%m-%dT%H:%M:%S')
    # calendar.timegm treats the tuple as GMT
    return calendar.timegm(when)

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

    self.labels = [x["name"].strip() for x in labels]

  def GetLabelsAsString(self):
    """Returns the labels as a comma delimited list of strings."""
    if self.labels is None:
      return None
    lst = list(self.labels)
    lst.sort()
    return ','.join(lst)
