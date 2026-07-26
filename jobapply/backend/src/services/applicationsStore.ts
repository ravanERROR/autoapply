import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'csv-parse/sync';
import { stringify } from 'csv-stringify/sync';
import { APPLICATIONS_CSV } from '../config.js';

export const APPLICATION_HEADERS = [
  'id',
  'timestamp',
  'platform',
  'jobTitle',
  'company',
  'location',
  'jobUrl',
  'status',
  'appliedAt',
  'notes',
] as const;

export type ApplicationRecord = Record<(typeof APPLICATION_HEADERS)[number], string>;

const CSV_HEADER = stringify([APPLICATION_HEADERS]);

function hasExpectedHeader(contents: string): boolean {
  const withoutBom = contents.replace(/^\uFEFF/, '');
  const firstLine = withoutBom.split(/\r?\n/, 1)[0];

  try {
    const rows = parse(firstLine, {
      relax_column_count: true,
      skip_empty_lines: false,
    }) as string[][];
    return APPLICATION_HEADERS.every((header, index) => rows[0]?.[index] === header)
      && rows[0]?.length === APPLICATION_HEADERS.length;
  } catch {
    return false;
  }
}

export function ensureApplicationsCsv(): void {
  fs.mkdirSync(path.dirname(APPLICATIONS_CSV), { recursive: true });

  if (!fs.existsSync(APPLICATIONS_CSV)) {
    fs.writeFileSync(APPLICATIONS_CSV, CSV_HEADER, 'utf8');
    return;
  }

  const contents = fs.readFileSync(APPLICATIONS_CSV, 'utf8');
  if (contents.trim().length === 0) {
    fs.writeFileSync(APPLICATIONS_CSV, CSV_HEADER, 'utf8');
    return;
  }

  if (!hasExpectedHeader(contents)) {
    const withoutBom = contents.replace(/^\uFEFF/, '');
    fs.writeFileSync(APPLICATIONS_CSV, `${CSV_HEADER}${withoutBom}`, 'utf8');
  }
}

export function readApplications(): ApplicationRecord[] {
  ensureApplicationsCsv();
  const contents = fs.readFileSync(APPLICATIONS_CSV, 'utf8');
  const rows = parse(contents, {
    bom: true,
    columns: true,
    relax_column_count: true,
    skip_empty_lines: true,
  }) as Record<string, string>[];

  return rows.map((row) => Object.fromEntries(
    APPLICATION_HEADERS.map((header) => [header, String(row[header] ?? '')]),
  ) as ApplicationRecord);
}

export function appendApplication(application: ApplicationRecord): void {
  ensureApplicationsCsv();
  const existingContents = fs.readFileSync(APPLICATIONS_CSV, 'utf8');
  if (existingContents.length > 0 && !existingContents.endsWith('\n') && !existingContents.endsWith('\r')) {
    fs.appendFileSync(APPLICATIONS_CSV, '\n', 'utf8');
  }
  const row = APPLICATION_HEADERS.map((header) => application[header]);
  fs.appendFileSync(APPLICATIONS_CSV, stringify([row]), 'utf8');
}

export function clearApplications(): void {
  fs.mkdirSync(path.dirname(APPLICATIONS_CSV), { recursive: true });
  fs.writeFileSync(APPLICATIONS_CSV, CSV_HEADER, 'utf8');
}

export function getApplicationsCsvPath(): string {
  return APPLICATIONS_CSV;
}
