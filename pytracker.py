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
import time
import urllib
import urllib2
import json

DEFAULT_BASE_API_URL = 'https://www.pivotaltracker.com/services/v5/'

class Resource(object):
  def __init__(self, attributes, data):
    for attr in attributes:
      setattr(self, attr, self.GetDataFromIndex(data, attr))

  def __str__(self):
    return "%s(%r)" % (self.kind.upper(), self.__dict__)

  def GetDataFromIndex(self, data, index):
    """Retrieve value associated with the index, if any.

    Args:
      data: JSON object
      index: name of the desired index

    Returns:
      None (if index doesn't exist), empty string (if index exists, but
      value is empty), or the index value.
    """
    if not index in data:
      return None
    elif not data[index]:
      return ''
    else:
      return data.get(index)

  def ParseDatetimeIntoSecs(self, data):
    """Returns the time parsed into seconds-since-epoch."""

    if not data:
      return None
    # Tracker emits datetime strings in UTC or GMT.
    # The [:-4] strips the timezone indicator
    when = time.strptime(data[:-2], '%Y-%m-%dT%H:%M:%S')
    # calendar.timegm treats the tuple as GMT
    return calendar.timegm(when)

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

    Args:
      data: A JSON object.
    Returns:
      boolean: True or False if the JSON is valid.

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

  def _ApiWrapper(self, endpoint, query=None):
    if query:
      output = self._Api(endpoint + query, 'GET')
    else:
      output = self._Api(endpoint, 'GET')

    if(self._ValidateJson(output)):
      return output

  def GetStories(self, filt=None):
    """Fetch all Stories that satisfy the filter.

    Args:
      filt: a Tracker search filter.
    Returns:
      List of Story().
    """
    if filt:
      data = self._ApiWrapper('stories', '?filter='+ urllib.quote_plus(filt))
    else:
      data = self._ApiWrapper('stories')

    stories = json.loads(data)
    lst = []
    for story in stories:
      lst.append(Story(story))

    return lst

  def GetStory(self, story_id):
    """Fetch a specific story by its ID.

    Args:
      story_id: A Story ID.
    Returns:
      A Story() object.
    """
    data = self._ApiWrapper('stories/%d' % story_id)
    story = json.loads(data)
    return Story(story)

  def GetProjectMemberships(self):
    """Fetch project memberships"""
    data = self._ApiWrapper('memberships')
    memberships = json.loads(data)
    lst = []
    for member in memberships:
      lst.append(ProjectMemberships(member))
    return lst

  def GetStoryComments(self, story_id):
    """Fetch all comments for a given Story ID.

    Args:
      story_id: A Story ID.
    Returns:
      List of Comment().
    """
    data = self._ApiWrapper('stories/%d/comments' % story_id)
    comments = json.loads(data)
    lst = []
    for comment in comments:
      lst.append(Comment(comment))

    return lst

  def GetStoryActivity(self, story_id, query=None):
    if query:
      data = self._ApiWrapper('stories/%d/activity?%s' % (story_id, query))
    else:
      data = self._ApiWrapper('stories/%d/activity' % story_id)

    activities = json.loads(data)
    lst = []
    for activity in activities:
      lst.append(Activity(activity))

    return lst

  def AddComment(self, story_id, comment):
    """Add a comment to a Story.

    Args:
      story_id: A Story ID.
      comment: A string that will be added a comment to the story.
    """
    comment = json.dumps({'text':comment})
    self._Api('stories/%d/comments' % int(story_id), 'POST', comment)

  def GetPersonById(self, memberships, id):
    """Search the provided memberships for the given id and return the Person"""
    for m in memberships:
      if m.person.id == id:
        return m.person
    return None

class TrackerApiException(Exception):
  """Raised when Tracker returns an error."""

class Person(Resource):
  """Represents a person."""

  def __init__(self, data):
    attributes = ['id', 'name', 'email', 'initials', 'username', 'kind']
    super(Person, self).__init__(attributes, data)

class ProjectMemberships(Resource):
  """Represents the Project Memberships.

  This class can be used to represent a complete Project Memebership.

  Internally, ProjectMemberships will be used to cross-reference a person_id
  with a Person to retrive information such as their name, email, etc.
  """

  def __init__(self, data):
    attributes = ['id', 'person', 'project_id', 'role', 'project_color',
      'last_viewed_at', 'wants_comment_notification_emails',
      'will_receive_mention_notifications_or_emails', 'kind']
    super(ProjectMemberships, self).__init__(attributes, data)

    # Special handling for last_viewed_at to parse datetime
    self.last_viewed_at = self.ParseDatetimeIntoSecs(self.last_viewed_at)

    #
    # The person may be a person_id or person resource. If we have a resource,
    # pass the data to Person(), otherwise store the person_id.
    #
    person_data = self.GetDataFromIndex(data, 'person')
    if isinstance(person_data, dict):
      self.person = Person(person_data)
    else:
      self.person = person_data

class Story(Resource):
  def __init__(self, data):
    attributes = ['id', 'project_id', 'name', 'description', 'story_type',
      'current_state', 'estimate', 'accepted_at', 'deadline', 'requested_by_id',
      'owner_ids', 'labels', 'created_at', 'updated_at', 'url', 'kind']
    super(Story, self).__init__(attributes, data)

    # Special handling for attributes to parse datetime
    self.created_at = self.ParseDatetimeIntoSecs(self.created_at)
    self.updated_at = self.ParseDatetimeIntoSecs(self.updated_at)
    self.deadline =self.ParseDatetimeIntoSecs(self.deadline)

    # Special handling for labels, we just want the "name"
    labels = self.GetDataFromIndex(data, 'labels')
    if labels is not None:
      self.AddLabelsFromArray(labels)

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

class Comment(Resource):
  """Represents a Comment.

  This class can be used to represent a complete Comment or be used to create a
  comment on a given resource.

  Internally, Comment will be associated with other classes which are
  instantiations of Pivotal Tracker resources, such as a Story, Epic, etc.
  """

  def __init__(self, data):
    attributes = ['id', 'story_id', 'epic_id', 'text', 'person_id',
      'created_at', 'updated_at', 'file_attachment_ids',
      'google_attachment_ids', 'commit_identifier', 'commit_type', 'kind']
    super(Comment, self).__init__(attributes, data)

    # Special handling for attributes to parse datetime
    self.created_at = self.ParseDatetimeIntoSecs(self.created_at)
    self.updated_at = self.ParseDatetimeIntoSecs(self.updated_at)

class Activity(Resource):
  """Represents an Activity.

  There are four different Activity endpoints. Their parameters are all common.
  The difference between them is that each implicity filters the activity
  selected for the response by different criteria.

  Information from all of these endpoints is returned in reverse chronologic
  order, so that the first activity in a response indicates the most recently
  made modification to the project.

  To read more about the four different endpoint:
  https://www.pivotaltracker.com/help/api#Activity_Information
  """

  def __init__(self, data):
    """Initialize Activity attributes."""

    attributes = ['kind', 'guid', 'project_version', 'message', 'highlight',
      'changes', 'primary_resource', 'project_id', 'performed_by_id',
      'occurred_at']
    super(Activity, self).__init__(attributes, data)

    # Special handling for attributes to parse datetime
    self.occurred_at = self.ParseDatetimeIntoSecs(self.occurred_at)
