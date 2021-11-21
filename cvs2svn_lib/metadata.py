# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2008 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs.
# ====================================================================

"""Represent CVSRevision metadata."""


class Metadata(object):
  def __init__(self, id, author, log_msg):
    self.id = id
    self.author = author
    self.log_msg = log_msg


