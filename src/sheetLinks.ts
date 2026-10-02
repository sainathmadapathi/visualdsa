import type { SheetRow } from './types';

export const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; } };
/** Where the sheet lists the problem comes first: its page on the sheet's own site. */
export const mainLink = (row: SheetRow) => row.source || row.url;
/** Other links attached to the problem (LeetCode, GfG): alternatives, used only when the main page can't be read. */
export const otherLinks = (row: SheetRow) => [...new Set([row.url, ...(row.links ?? [])])].filter(link => !!link && link !== mainLink(row));
const isLeetcode = (link: string) => /(^|\.)leetcode\.com$/.test(host(link));
/** A row with a page that can be read (LeetCode builds its pages in the browser). */
export const readable = (row: SheetRow) => [mainLink(row), ...otherLinks(row)].some(link => !!link && !isLeetcode(link));
