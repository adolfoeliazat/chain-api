from django.test import TestCase
from doppel2.core.models import ScalarData, Unit, Metric, Device, Sensor, Site
from doppel2.core.api import Resource
from datetime import datetime
from django.db.models import Avg
import json
from doppel2.core.api import HTTP_STATUS_SUCCESS, HTTP_STATUS_CREATED
from django.utils.timezone import make_aware, utc

BASE_API_URL = '/api/'
SCALAR_DATA_URL = BASE_API_URL + 'scalar_data/'
SITES_URL = BASE_API_URL + 'sites/'


ACCEPT_TAIL = 'application/xhtml+xml,application/xml;q=0.9,\
        image/webp,*/*;q=0.8'


class DoppelTestCase(TestCase):
    def setUp(self):
        self.unit = Unit(name='C')
        self.unit.save()
        self.temp_metric = Metric(name='Temperature')
        self.temp_metric.save()
        self.setpoint_metric = Metric(name='Setpoint')
        self.setpoint_metric.save()
        self.sites = [Site(name='Test Site 1'), Site(name='Test Site 2')]
        for site in self.sites:
            site.save()
        num_devices = 5
        self.devices = [Device(name='Thermostat %d' % i,
                               site=self.sites[i % len(self.sites)])
                        for i in range(0, num_devices)]
        self.sensors = []
        for device in self.devices:
            device.save()
            self.sensors.append(Sensor(device=device,
                                       metric=self.temp_metric,
                                       unit=self.unit))
            self.sensors.append(Sensor(device=device,
                                       metric=self.setpoint_metric,
                                       unit=self.unit))
        self.scalar_data = []
        for sensor in self.sensors:
            sensor.save()
            self.scalar_data.append(ScalarData(
                sensor=sensor,
                timestamp=make_aware(datetime(2013, 1, 1, 0, 0, 1), utc),
                value=22.0))
            self.scalar_data.append(ScalarData(
                sensor=sensor,
                timestamp=make_aware(datetime(2013, 1, 1, 0, 0, 2), utc),
                value=23.0))
        for data in self.scalar_data:
            data.save()

    def get_resource(self, url, mime_type='application/json'):
        accept_header = mime_type + ',' + ACCEPT_TAIL
        response = self.client.get(url,
                                   HTTP_ACCEPT=accept_header)
        self.assertEqual(response.status_code, HTTP_STATUS_SUCCESS)
        self.assertEqual(response['Content-Type'], mime_type)
        if mime_type == 'application/json':
            return json.loads(response.content)
        return response.content

    def post_resource(self, url, resource, mime_type='application/json'):
        accept_header = mime_type + ',' + ACCEPT_TAIL
        response = self.client.post(url, json.dumps(resource),
                                    content_type=mime_type,
                                    HTTP_ACCEPT=accept_header)
        self.assertEqual(response.status_code, HTTP_STATUS_CREATED)
        self.assertEqual(response['Content-Type'], mime_type)
        data = json.loads(response.content)
        return data

    def get_a_site(self, mime_type='application/json'):
        '''GETs a site through the API for testing'''
        base_response = self.get_resource(BASE_API_URL, mime_type=mime_type)
        sites = base_response['sites']['data']
        site_url = sites[0]['_href']
        # following the link like a good RESTful client
        return self.get_resource(site_url, mime_type=mime_type)

    def get_a_device(self, mime_type='application/json'):
        '''GETs a device through the API for testing'''
        site = self.get_a_site(mime_type=mime_type)
        devices_url = site['devices']['_href']
        devices = self.get_resource(devices_url, mime_type=mime_type)
        device_url = devices['data'][0]['_href']
        return self.get_resource(device_url, mime_type=mime_type)

    def get_a_sensor(self, mime_type='application/json'):
        device = self.get_a_device(mime_type=mime_type)
        sensors_url = device['sensors']['_href']
        sensors = self.get_resource(sensors_url, mime_type=mime_type)
        sensor_url = sensors['data'][0]['_href']
        return self.get_resource(sensor_url, mime_type=mime_type)


class SensorDataTest(DoppelTestCase):
    def test_data_can_be_added(self):
        data = ScalarData(sensor=self.sensors[0], value=25)
        data.save()
        self.assertEqual(data.value, 25)

    def test_largeish_datasets_can_be_queried_quickly(self):
        sensor = Sensor(device=self.devices[0], metric=self.temp_metric,
                        unit=self.unit)
        sensor.save()
        data = [ScalarData(sensor=sensor, value=val)
                for val in range(10000)]
        ScalarData.objects.bulk_create(data)
        avg = 0
        start_time = datetime.now()
        #for data in ScalarData.objects.all():
        #    avg += data.value
        #avg = avg / ScalarData.objects.all().count()
        avg = sensor.scalar_data.all().aggregate(Avg('value'))['value__avg']
        end_time = datetime.now()
        elapsed_time = end_time - start_time
        self.assertEqual(avg, 4999.5)
        self.assertLess(elapsed_time.total_seconds(), 0.1)


class ApiTest(DoppelTestCase):
    def test_base_url_should_have_href(self):
        data = self.get_resource(BASE_API_URL)
        self.assertRegexpMatches(data['_href'], 'http://.*' + BASE_API_URL)

    def test_base_url_should_have_sites_collection(self):
        data = self.get_resource(BASE_API_URL)
        sites_coll = data['sites']
        self.assertRegexpMatches(sites_coll['_href'], 'http://.*' + SITES_URL)

    def test_base_sites_collection_should_have_metadata(self):
        data = self.get_resource(BASE_API_URL)
        sites_coll = data['sites']
        self.assertEqual(sites_coll['meta']['totalCount'], len(self.sites))

    def test_sites_should_be_expanded_in_base_url(self):
        response = self.get_resource(BASE_API_URL)
        sites = response['sites']['data']
        self.assertIn(sites[0]['name'], [self.sites[0].name,
                                         self.sites[1].name])

    def test_site_disp_field_should_be_name(self):
        site = self.get_a_site()
        self.assertEqual(site['name'], site['_disp'])

    def test_collections_should_have_disp_field(self):
        site = self.get_a_site()
        self.assertIn('_disp', site['devices'])

    def test_sites_should_be_postable(self):
        new_site = {
            "_type": "site",
            "latitude": 42.360461,
            "longitude": -71.087347,
            "name": "MIT Media Lab"
        }
        response = self.post_resource(SITES_URL, new_site)
        db_obj = Site.objects.get(name='MIT Media Lab')
        for field in ['latitude', 'longitude', 'name']:
            self.assertEqual(new_site[field], response[field])
            self.assertEqual(new_site[field], getattr(db_obj, field))

    def test_devices_should_be_postable_to_a_site(self):
        sites_coll = self.get_resource(SITES_URL)['data']
        dev_url = sites_coll[0]['devices']['_href']
        new_device = {
            "_type": "device",
            "building": "E14",
            "description": "A great device",
            "floor": "5",
            "name": "Thermostat 42",
            "room": "E14-548R"
        }
        self.post_resource(dev_url, new_device)
        db_device = Device.objects.get(name=new_device['name'])
        db_site = Site.objects.get(name=sites_coll[0]['name'])
        self.assertEqual(db_device.site, db_site)

    def test_sensors_should_be_postable_to_existing_device(self):
        sites_coll = self.get_resource(SITES_URL)['data']
        dev_url = sites_coll[0]['devices']['_href']
        device = self.get_resource(dev_url)['data'][0]

        pressure_metric = Metric(name='Pressure')
        pressure_metric.save()

        dev_href = device['sensors']['_href']
        new_sensor = {
            "_type": "sensor",
            'metric': 'Pressure',
            'unit': 'C',
            'value': 0,
            'timestamp': 0,
        }
        self.post_resource(dev_href, new_sensor)
        db_sensor = Sensor.objects.get(metric=pressure_metric)
        self.assertEqual(pressure_metric, db_sensor.metric)

    def test_sensors_should_be_postable_to_newly_posted_device(self):
        sites_coll = self.get_resource(SITES_URL)['data']
        dev_url = sites_coll[0]['devices']['_href']

        new_device = {
            "_type": "device",
            "building": "E14",
            "description": "A great device",
            "floor": "5",
            "name": "Thermostat 42",
            "room": "E14-548R"
        }
        device = self.post_resource(dev_url, new_device)

        pressure_metric = Metric(name='Pressure')
        pressure_metric.save()
        dev_href = device['sensors']['_href']
        new_sensor = {
            "_type": "sensor",
            'metric': 'Pressure',
            'unit': 'C',
            'value': 0,
            'timestamp': 0,
        }
        self.post_resource(dev_href, new_sensor)
        db_sensor = Sensor.objects.get(metric=pressure_metric)
        self.assertEqual(pressure_metric, db_sensor.metric)

    def test_site_resource_should_have_devices(self):
        site = self.get_a_site()
        device_coll = self.get_resource(site['devices']['_href'])
        db_site = Site.objects.get(name=site['name'])
        self.assertEqual(len(device_coll['data']),
                         db_site.devices.count())

    def test_devices_can_be_filtered_by_site(self):
        full_devices_coll = self.get_resource(BASE_API_URL + 'devices/')
        filtered_devices_coll = self.get_resource(
            BASE_API_URL + 'devices/?site=%d' % self.sites[0].id)
        self.assertEqual(len(full_devices_coll['data']), 5)
        self.assertEqual(len(filtered_devices_coll['data']), 3)

    def test_filtered_collection_has_filtered_url(self):
        site_id = self.sites[0].id
        coll = self.get_resource(
            BASE_API_URL + 'devices/?site=%d' % site_id)
        self.assertTrue(('site=%d' % site_id) in coll['_href'])

    def test_device_resource_should_have_sensors(self):
        device = self.get_a_device()
        self.assertIn('sensors', device)
        self.assertIn('_href', device['sensors'])

    def test_site_should_link_to_device_coll(self):
        site = self.get_a_site()
        # a link is a resource with only _href and _disp fields
        self.assertIn('_href', site['devices'])
        self.assertIn('_disp', site['devices'])
        self.assertEquals(2, len(site['devices']))

    def test_sensor_should_have_data_url(self):
        sensor = self.get_a_sensor()
        self.assertIn('_href', sensor['history'])

    def test_sensor_data_should_have_timestamp_and_value(self):
        sensor = self.get_a_sensor()
        sensor_data = self.get_resource(sensor['history']['_href'])
        self.assertIn('timestamp', sensor_data['data'][0])
        self.assertIn('value', sensor_data['data'][0])

    def test_sensor_should_have_parent_link(self):
        sensor = self.get_a_sensor()
        self.assertIn('device', sensor)

    def test_sensor_data_should_be_postable(self):
        sensor = self.get_a_sensor()
        data_url = sensor['history']['_href']
        timestamp = make_aware(datetime(2013, 1, 1, 0, 0, 0), utc)
        data = {
            'value': 23,
            'timestamp': timestamp.isoformat()
        }
        self.post_resource(data_url, data)
        # TODO: actually make sure the posted data is correct

    def test_device_collections_should_limit_to_default_page_size(self):
        site = self.get_a_site()
        devs_url = site['devices']['_href']
        # make sure we create more devices than will fit on a page
        for i in range(0, Resource.page_size + 1):
            dev = {'name': 'test dev %d' % i}
            self.post_resource(devs_url, dev)
        devs = self.get_resource(devs_url)
        self.assertEqual(len(devs['data']), Resource.page_size)

    def test_pages_should_have_next_and_prev_links(self):
        site = self.get_a_site()
        devs_url = site['devices']['_href']
        # make sure we create more devices than will fit on a page
        for i in range(0, Resource.page_size + 1):
            dev = {'name': 'test dev %d' % i}
            self.post_resource(devs_url, dev)
        devs = self.get_resource(devs_url)
        self.assertIn('next', devs['meta'])
        self.assertNotIn('previous', devs['meta'])
        next_devs = self.get_resource(devs['meta']['next']['_href'])
        self.assertIn('previous', next_devs['meta'])
        self.assertNotIn('next', next_devs['meta'])


#    def test_scalar_data_should_be_gettable_from_api(self):
#        data = ScalarData(sensor=self.sensors[0], value=25)
#        data.save()
#        data = self.get_resource(SCALAR_DATA_URL)['data']
#        self.assertEqual(len(data), 1)
#        self.assertEqual(data[0]['value'], 25)
#
#    def test_scalar_data_should_return_total_in_meta(self):
#        data = ScalarData(sensor=self.sensor, value=25)
#        data.save()
#        # clear the id so we re-insert instead of updating
#        data.id = None
#        data.save()
#        metadata = self.get_resource(SCALAR_DATA_URL)['meta']
#        self.assertEqual(metadata['total_count'], 2)


class HTMLTests(DoppelTestCase):
    def test_root_request_accepting_html_gets_it(self):
        res = self.get_resource(BASE_API_URL, mime_type='text/html').strip()
        # check that it startswith a doctype
        self.assertTrue(res.startswith("<!DOCTYPE html"))
        self.assertTrue(res.endswith("</html>"))


#class ScalarDataFilteringApiTest(DoppelTestCase):
#    def setUp(self):
#        DoppelTestCase.setUp(self)
#        device = Device(site=self.site, name="Thermostat")
#        device.save()
#        sensor1 = Sensor(unit=self.unit, device=device,
#                         metric=self.metric)
#        sensor1.save()
#        sensor2 = Sensor(unit=self.unit, device=device,
#                         metric=self.metric)
#        sensor2.save()
#        data = []
#        for value, hour in zip([20, 21, 23, 27], [2, 4, 6, 8]):
#            data.append(
#                ScalarData(sensor=sensor1, value=value,
#                           timestamp=make_aware(
#                               datetime(2013, 4, 12, hour, 0, 0), utc)))
#            data.append(
#                ScalarData(sensor=sensor2, value=value,
#                           timestamp=make_aware(
#                               datetime(2013, 4, 12, hour, 0, 0), utc)))
#        ScalarData.objects.bulk_create(data)
#
#    def test_scalar_data_should_accept_a_date_range(self):
#        # create a date range that should only grab the middle 2 data points
#        query_string = ('?timestamp__gt=2013-04-12T03:30:00Z&' +
#                        'timestamp__lt=2013-04-12T06:30:00Z')
#        url = SCALAR_DATA_URL + query_string
#        data = self.get_resource(url)['data']
#        self.assertEqual(len(data), 4)
#
#    def test_scalar_data_should_accept_average(self):
#        query_string = ('?timestamp__gt=2013-04-12T03:30:00Z&' +
#                        'timestamp__lt=2013-04-12T06:30:00Z&' +
#                        'average_by=value')
#        url = SCALAR_DATA_URL + query_string
#        data = self.get_resource(url)
#        self.assertEqual(data['average_value'], 22)
