"""Run with python -m unittest discover -s tests -v (Python 3.10+)."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import random
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('subnet_app', ROOT/'backend/subnet_app_1.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class SubnetTests(unittest.TestCase):
    def test_prefixes_match_standard_library(self):
        rng = random.Random(42)
        for prefix in range(33):
            for _ in range(12):
                address = str(ipaddress.IPv4Address(rng.randrange(2**32)))
                network = ipaddress.IPv4Network(f'{address}/{prefix}', strict=False)
                result = backend.compute_locally(address, '/'+str(prefix))
                self.assertEqual(result['network'], str(network.network_address))
                self.assertEqual(result['broadcast'], str(network.broadcast_address))
                self.assertEqual(result['num_hosts'], network.num_addresses if prefix >= 31 else network.num_addresses - 2)
                self.assertEqual(result, backend.compute_locally(address, str(network.netmask)))

    def test_small_networks(self):
        for prefix, first, last, count in [(31,'10.0.0.0','10.0.0.1',2),(32,'10.0.0.1','10.0.0.1',1)]:
            result=backend.compute_locally('10.0.0.1',str(prefix))
            self.assertEqual((result['first_host'],result['last_host'],result['num_hosts']), (first,last,count))

    def test_invalid_input(self):
        cases=[('300.1.1.1','24'),('1.2.3','24'),('1.2.3.-1','24'),('01.2.3.4','24'),('::1','24'),('24','24'),('1.2.3.4','33'),('1.2.3.4','/33'),('1.2.3.4','-1'),('1.2.3.4','255.0.255.0'),('1.2.3.4','0.0.0.255'),('1.2.3.4','255.255.255.256'),('1.2.3.4','24.0'),(None,'24'),('1.2.3.4',24)]
        for ip,mask in cases:
            with self.subTest(ip=ip,mask=mask): self.assertIn('error',backend.compute_locally(ip,mask))

    def test_api_validation(self):
        client=backend.app.test_client()
        for payload in [[],{}, {'ip':123,'mask':'24'}, {'ip':'1.2.3.4','mask':'/33'}, {'ip':'1.2.3.4','mask':'24','mode':'bad'}, {'ip':'1.2.3.4','mask':'24','mode':'tcp'}]:
            self.assertEqual(client.post('/api/calculate',json=payload).status_code,400)
        self.assertEqual(client.post('/api/calculate',data='broken',content_type='application/json').status_code,400)
        self.assertEqual(client.post('/api/calculate',json={'ip':'10.0.0.1','mask':'31'}).json['num_hosts'],2)
        self.assertEqual(client.get('/').status_code,200)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for browser/Python parity testing')
    def test_browser_python_parity(self):
        rng=random.Random(99)
        cases=[(str(ipaddress.IPv4Address(rng.randrange(2**32))),str(prefix)) for prefix in range(33) for _ in range(10)]
        cases += [('10.0.0.1','255.255.255.0'),('10.0.0.1','/31'),('10.0.0.1','/32'),('10.0.0.1','/33'),('999.0.0.1','24'),('10.0.0.1','0.0.0.255'),('10.0.0.1','255.0.255.0')]
        program="const {calculateSubnet}=require('./docs/subnet.js');const fs=require('fs');console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(([ip,m])=>{try{return calculateSubnet(ip,m)}catch(e){return {error:e.message}}})));"
        result=subprocess.run(['node','-e',program],cwd=ROOT,input=json.dumps(cases),capture_output=True,text=True,check=True)
        for (ip,mask),actual in zip(cases,json.loads(result.stdout)):
            expected=backend.compute_locally(ip,mask)
            if 'error' in expected: self.assertIn('error',actual)
            else:
                for key in expected:
                    if key!='source': self.assertEqual(actual[key],expected[key],(ip,mask,key))

if __name__=='__main__': unittest.main()
