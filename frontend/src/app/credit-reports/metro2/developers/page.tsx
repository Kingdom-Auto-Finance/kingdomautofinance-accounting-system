'use client';

import { useEffect, useState } from 'react';
import { metro2API, type Metro2Schema } from '@/lib/api';

const ENDPOINTS = [
  ['GET', '/api/v1/credit-reports/metro2/schema'],
  ['GET', '/api/v1/credit-reports/metro2/account'],
  ['POST', '/api/v1/credit-reports/metro2/upload'],
  ['POST', '/api/v1/credit-reports/metro2/upload/validate'],
  ['POST', '/api/v1/credit-reports/metro2/upload/accept'],
  ['GET', '/api/v1/credit-reports/metro2/mapping-templates'],
  ['POST', '/api/v1/credit-reports/metro2/mapping-templates'],
  ['GET', '/api/v1/credit-reports/metro2/records'],
  ['POST', '/api/v1/credit-reports/metro2/records'],
  ['PATCH', '/api/v1/credit-reports/metro2/records/{id}'],
  ['POST', '/api/v1/credit-reports/metro2/records/{id}/deactivate'],
  ['POST', '/api/v1/credit-reports/metro2/records/{id}/revalidate'],
  ['GET', '/api/v1/credit-reports/metro2/analytics'],
  ['POST', '/api/v1/credit-reports/metro2/files/generate'],
  ['GET', '/api/v1/credit-reports/metro2/files'],
  ['GET', '/api/v1/credit-reports/metro2/files/{id}/download'],
  ['GET', '/api/v1/credit-reports/metro2/transmissions'],
  ['POST', '/api/v1/credit-reports/metro2/transmissions'],
  ['GET', '/api/v1/credit-reports/metro2/responses'],
  ['POST', '/api/v1/credit-reports/metro2/responses/upload'],
  ['GET', '/api/v1/credit-reports/metro2/disputes'],
  ['POST', '/api/v1/credit-reports/metro2/disputes'],
  ['PATCH', '/api/v1/credit-reports/metro2/disputes/{id}'],
];

export default function DevelopersPage() {
  const [schema, setSchema] = useState<Metro2Schema | null>(null);
  useEffect(() => {
    metro2API.getSchema().then(setSchema).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <div className="font-medium mb-2">Endpoints</div>
        <div className="border rounded bg-white overflow-hidden text-sm">
          <table className="w-full">
            <thead className="bg-gray-50 text-left">
              <tr>
                <th className="px-3 py-2 w-20">Method</th>
                <th className="px-3 py-2">Path</th>
              </tr>
            </thead>
            <tbody>
              {ENDPOINTS.map(([m, p], i) => (
                <tr key={i} className="border-t">
                  <td className="px-3 py-1.5 font-mono text-xs">{m}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{p}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Full OpenAPI schema available at{' '}
          <a href="/docs" className="underline">
            /docs
          </a>
          .
        </p>
      </div>

      {schema && (
        <div>
          <div className="font-medium mb-2">
            Metro 2 schema ({schema.counts.total} fields,{' '}
            {schema.counts.required} required)
          </div>
          <div className="border rounded bg-white overflow-hidden text-sm">
            <table className="w-full">
              <thead className="bg-gray-50 text-left">
                <tr>
                  <th className="px-3 py-2">Pos</th>
                  <th className="px-3 py-2">Len</th>
                  <th className="px-3 py-2">Field</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Importance</th>
                  <th className="px-3 py-2">Format</th>
                </tr>
              </thead>
              <tbody>
                {schema.fields.map(f => (
                  <tr key={f.name} className="border-t">
                    <td className="px-3 py-1.5 font-mono text-xs">{f.position}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{f.length}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{f.name}</td>
                    <td className="px-3 py-1.5 text-xs">{f.type}</td>
                    <td className="px-3 py-1.5 text-xs">{f.importance}</td>
                    <td className="px-3 py-1.5 text-xs text-muted-foreground">
                      {f.format}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
