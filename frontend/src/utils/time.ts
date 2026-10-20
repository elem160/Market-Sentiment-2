/**
 * Time and timezone formatting utilities.
 * Handles ET (America/New_York) with full DST awareness and UTC formatting.
 */

export function parseDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}

export function formatInTimeZone(
  iso: string | Date,
  timeZone: string,
  options?: Intl.DateTimeFormatOptions
): string {
  const d = parseDate(iso);
  if (!d) return '—';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    timeZone,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    ...options,
  };

  return new Intl.DateTimeFormat('en-US', defaultOptions).format(d);
}

export function formatUtc(iso: string | Date, options?: Intl.DateTimeFormatOptions): string {
  return formatInTimeZone(iso, 'UTC', options);
}

export function formatEt(iso: string | Date, options?: Intl.DateTimeFormatOptions): string {
  return formatInTimeZone(iso, 'America/New_York', options);
}

export function formatSessionRange(
  startIso: string | Date,
  endIso: string | Date,
  timeZone: string = 'America/New_York'
): string {
  const s = parseDate(startIso);
  const e = parseDate(endIso);
  if (!s || !e) return '—';

  const timeOpts: Intl.DateTimeFormatOptions = {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  };
  const dateOpts: Intl.DateTimeFormatOptions = {
    timeZone,
    month: 'short',
    day: 'numeric',
  };

  const dateStr = new Intl.DateTimeFormat('en-US', dateOpts).format(s);
  const startStr = new Intl.DateTimeFormat('en-US', timeOpts).format(s);
  const endStr = new Intl.DateTimeFormat('en-US', timeOpts).format(e);

  return `${dateStr}, ${startStr} – ${endStr}`;
}

export function formatArticleAge(ageHours: number | null | undefined): string {
  if (ageHours === null || ageHours === undefined || isNaN(ageHours)) return '';
  if (ageHours < 1) {
    const mins = Math.max(1, Math.round(ageHours * 60));
    return `${mins}m ago`;
  }
  return `${ageHours.toFixed(1)}h ago`;
}
