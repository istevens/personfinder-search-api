#!/usr/bin/python2.5
# Copyright 2010 Google Inc.
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

"""Basic API for reading/writing small numbers of records."""

__author__ = 'kpy@google.com (Ka-Ping Yee)'

from datetime import datetime
import atom
import model
import utils
import importer
import pfif


class Read(utils.Handler):
    https_required = True

    def get(self):
        if self.config.read_auth_key_required and not (
            self.auth and self.auth.read_permission):
            self.response.set_status(403)
            self.write('Missing or invalid authorization key\n')
            return

        pfif_version = pfif.PFIF_VERSIONS.get(self.params.version or '1.2')

        # Note that self.request.get can handle multiple IDs at once; we
        # can consider adding support for multiple records later.
        record_id = self.request.get('id')
        if not record_id:
            return self.error(400, 'Missing id parameter')
        person = model.Person.get(self.subdomain, record_id)
        if not person:
            return self.error(404, 'No person record with ID %s' % record_id)
        notes = model.Note.get_by_person_record_id(self.subdomain, record_id)

        self.response.headers['Content-Type'] = 'application/xml'
        records = [pfif_version.person_to_dict(person)]
        note_records = map(pfif_version.note_to_dict, notes)
        utils.optionally_filter_sensitive_fields(records, self.auth)
        utils.optionally_filter_sensitive_fields(note_records, self.auth)
        pfif_version.write_file(
            self.response.out, records, lambda p: note_records)


class Write(utils.Handler):
    https_required = True

    def post(self):
        if not (self.auth and self.auth.domain_write_permission):
            self.response.set_status(403)
            self.write('Missing or invalid authorization key\n')
            return

        source_domain = self.auth.domain_write_permission
        try:
            person_records, note_records = \
                pfif.parse_file(self.request.body_file)
        except Exception, e:
            self.response.set_status(400)
            self.write('Invalid XML: %s\n' % e)
            return

        self.response.headers['Content-Type'] = 'application/xml'
        self.write('<?xml version="1.0"?>\n')
        self.write('<status:status>\n')

        create_person = importer.create_person
        written, skipped, total = importer.import_records(
            self.subdomain, source_domain, create_person, person_records)
        self.write_status(
            'person', written, skipped, total, 'person_record_id')

        create_note = importer.create_note
        written, skipped, total = importer.import_records(
            self.subdomain, source_domain, create_note, note_records)
        self.write_status(
            'note', written, skipped, total, 'note_record_id')

        self.write('</status:status>\n')

    def write_status(self, type, written, skipped, total, id_field):
        """Emit status information about the results of an attempted write."""
        skipped_records = []
        for error, record in skipped:
            skipped_records.append(
                '      <pfif:%s>%s</pfif:%s>\n' %
                (id_field, record.get(id_field, ''), id_field))
            skipped_records.append(
                '      <status:error>%s</status:error>\n' % error)

        self.write('''
  <status:write>
    <status:record_type>pfif:%s</status:record_type>
    <status:parsed>%d</status:parsed>
    <status:written>%d</status:written>
    <status:skipped>
%s
    </status:skipped>
  </status:write>
''' % (type, total, written, ''.join(skipped_records).rstrip()))

class Search(utils.Handler):
    https_required = False
    
    def get(self):
        pfif_version = pfif.PFIF_VERSIONS.get(self.params.version or '1.2')
        query_string = self.request.get("q")
        subdomain = self.request.get("subdomain")
        
        # backend not ready yet, so use a hardcoded stub instead
        records = model.Person.search(query_string, subdomain=subdomain)
        
        # format to PFIF
        records = [pfif_version.person_to_dict(p) for p in records]
        pfif_version.write_file(self.response.out, records)

if __name__ == '__main__':
    utils.run(('/api/read', Read), ('/api/write', Write), ('/api/search', Search))
