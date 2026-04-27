import { useState, useEffect, useCallback, useRef, type CSSProperties } from "react";
import type React from "react";
import type { JournalClubApi } from "../api";
import type { Journal, TocArticle, QueueItem } from "../types";

interface Props {
  api: JournalClubApi;
  isDesktop?: boolean;
}

type Scope = 1 | 3 | 6 | 12;
const SCOPE_LABELS: Record<Scope, string> = { 1: "Current issue", 3: "3 months", 6: "6 months", 12: "1 year" };

interface JournalState {
  toc: TocArticle[];
  loading: boolean;
  scope: Scope;
  excludedTypes?: Set<string>;
  excludedSubspecialties?: Set<Subspecialty>;
}

type Subspecialty = "Obstetrics" | "Onco-gynecology" | "Fertility" | "Ultrasound" | "Gynecology" | "Other";

const SUBSPECIALTY_ORDER: Subspecialty[] = ["Obstetrics", "Gynecology", "Onco-gynecology", "Fertility", "Ultrasound", "Other"];

// Order matters: more specific patterns checked first.
const SUBSPECIALTY_PATTERNS: Array<{ label: Subspecialty; re: RegExp }> = [
  { label: "Onco-gynecology", re: /\b(ovarian cancer|endometrial cancer|cervical cancer|vulvar cancer|vaginal cancer|gynecolog\w* (?:onc|cancer|malignan)|gynaecolog\w* (?:onc|cancer|malignan)|trophoblastic|brca|chemo(?:therapy)?|radiotherap|carcinom|neoplas|tumou?r|lymphoma|sarcoma|metastas|cancer screening|hpv vaccin|paclitaxel|cisplatin|olaparib|bevacizumab)\b/i },
  { label: "Fertility",       re: /\b(ivf|icsi|iui|in[- ]vitro fertili[sz]ation|art cycle|assisted reproduct|infertilit|subfertilit|oocyte|embryo(?:nic)? transfer|ovarian (?:reserve|stimulation)|amh\b|gonadotropin|fertility preservation|cryopreserv|recurrent (?:pregnancy )?loss|miscarriage|implantation failure)\b/i },
  { label: "Ultrasound",      re: /\b(ultrasound|sonograph|doppler|nuchal translucenc|3d (?:scan|ultrasound)|biophysical profile|cervical length measurement|transvaginal scan|fetal biometry|nt scan|anomaly scan)\b/i },
  { label: "Obstetrics",      re: /\b(pregnan|gestation|antenatal|prenatal|intrapartum|postpartum|peripartum|labou?r|deliver|cesarean|caesarean|c-section|vaginal birth|preeclamps|eclamps|gestational diabet|preterm|stillbirth|placenta(?:l|tion)?|amniotic|chorioamnioniti|fetal|foetal|neonatal|midwife|midwifery|obstetric|maternal mortality|maternal morbidity|hellp|oxytocin|epidural)\b/i },
  { label: "Gynecology",      re: /\b(menstr|menopaus|endometrios|fibroid|leiomyoma|adenomyos|polycystic ovar|pcos|hysterectom|myomectom|laparoscop|hysteroscop|colposcop|pelvic (?:pain|floor|organ prolapse)|incontinenc|urogyn|contracept|iud|sterilization|abortion|vulvodyn|dyspareun|pap smear|cervical screen|gynecolog|gynaecolog)\b/i },
];

function classifySubspecialty(article: TocArticle): Set<Subspecialty> {
  const text = `${article.title ?? ""} ${article.abstract ?? ""}`;
  const labels = new Set<Subspecialty>();
  if (!text.trim()) { labels.add("Other"); return labels; }
  for (const { label, re } of SUBSPECIALTY_PATTERNS) {
    if (re.test(text)) labels.add(label);
  }
  if (labels.size === 0) labels.add("Other");
  return labels;
}

type DlStatus = "idle" | "queued" | "downloading" | "done" | "failed";

function matchQueue(article: TocArticle, queue: QueueItem[]): QueueItem | undefined {
  return queue.find(q =>
    (article.pmid && q.input.includes(article.pmid)) ||
    (article.doi && q.input.toLowerCase().includes(article.doi.toLowerCase())) ||
    q.input === article.url
  );
}

function loadOrder(): string[] {
  try { return JSON.parse(localStorage.getItem("jc-journal-order") ?? "[]"); }
  catch { return []; }
}

function saveOrder(order: string[]) {
  localStorage.setItem("jc-journal-order", JSON.stringify(order));
}

interface PendingEmailBatch { pmids: string[]; queuedAt: number; }

const PENDING_KEY = "jc-pending-email-batch";

function loadPendingBatch(): PendingEmailBatch | null {
  try {
    const raw = localStorage.getItem(PENDING_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PendingEmailBatch;
    if (!parsed?.pmids?.length) return null;
    // Drop batches older than 24h to avoid retry-forever loops
    if (Date.now() - parsed.queuedAt > 24 * 60 * 60 * 1000) { localStorage.removeItem(PENDING_KEY); return null; }
    return parsed;
  } catch { return null; }
}

function savePendingBatch(batch: PendingEmailBatch) {
  localStorage.setItem(PENDING_KEY, JSON.stringify(batch));
}

function clearPendingBatch() { localStorage.removeItem(PENDING_KEY); }

export function JournalsPage({ api, isDesktop = false }: Props) {
  const [journals, setJournals] = useState<Journal[]>([]);
  const [journalStates, setJournalStates] = useState<Record<string, JournalState>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [journalOrder, setJournalOrder] = useState<string[]>(loadOrder);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [emailSet, setEmailSet] = useState<Set<string>>(new Set());
  const [emailSending, setEmailSending] = useState(false);
  const [search, setSearch] = useState("");
  const [followingId, setFollowingId] = useState<string | null>(null);
  const [hint, setHint] = useState<{ msg: string; kind: "info" | "error" } | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addName, setAddName] = useState("");
  const [addAbbr, setAddAbbr] = useState("");
  const [addIssn, setAddIssn] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const didAutoSelect = useRef(false);
  const queueRef = useRef(queue);
  queueRef.current = queue;

  // ── Data loading ────────────────────────────────────────────────────────────

  const loadTocForId = useCallback(async (journalId: string, scope: Scope) => {
    setJournalStates(prev => ({
      ...prev,
      [journalId]: { ...(prev[journalId] ?? { toc: [], scope, loading: false }), loading: true, scope },
    }));
    try {
      const toc = await api.getJournalToc(journalId, scope);
      setJournalStates(prev => ({ ...prev, [journalId]: { ...prev[journalId], toc, loading: false } }));
    } catch {
      setJournalStates(prev => ({ ...prev, [journalId]: { ...prev[journalId], loading: false } }));
    }
  }, [api]);

  useEffect(() => { api.getJournals().then(setJournals).catch(() => {}); }, [api]);

  const refreshDownloadedMap = useCallback(async () => {
    try {
      const r = await api.getArticles({ limit: 500 });
      const m: Record<string, string> = {};
      r.items.forEach(a => { if (a.pmid) m[a.pmid] = a.id; });
      return m;
    } catch { return {} as Record<string, string>; }
  }, [api]);

  // Auto-select first followed journal on initial load
  useEffect(() => {
    if (!journals.length || didAutoSelect.current || selectedId) return;
    const followedIds = journals.filter(j => j.is_following).map(j => j.id);
    if (!followedIds.length) return;
    didAutoSelect.current = true;

    const saved = loadOrder();
    const ordered = [...saved.filter(id => followedIds.includes(id)), ...followedIds.filter(id => !saved.includes(id))];
    setJournalOrder(ordered);
    saveOrder(ordered);

    const firstId = ordered[0];
    setSelectedId(firstId);
    loadTocForId(firstId, 1);
  }, [journals, selectedId, loadTocForId]);

  const refreshQueue = useCallback(() => {
    api.getQueue().then(setQueue).catch(() => {});
  }, [api]);
  useEffect(() => {
    refreshQueue();
    const t = setInterval(refreshQueue, 15000);
    return () => clearInterval(t);
  }, [refreshQueue]);

  // Pending-email batch poller: when all queued PMIDs are downloaded, send the email.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const batch = loadPendingBatch();
      if (!batch) return;
      const dl = await refreshDownloadedMap();
      if (cancelled) return;
      const ids = batch.pmids.map(p => dl[p]).filter(Boolean) as string[];
      if (ids.length < batch.pmids.length) return;
      try {
        await api.emailArticles(ids);
        clearPendingBatch();
        showHint(`Auto-sent ${ids.length} article${ids.length > 1 ? "s" : ""} to your email ✓`);
      } catch {
        // Leave the batch in place; next tick will retry.
      }
    };
    tick();
    const t = setInterval(tick, 10000);
    return () => { cancelled = true; clearInterval(t); };
  }, [api, refreshDownloadedMap]);

  // ── UI helpers ───────────────────────────────────────────────────────────────

  const showHint = (msg: string, kind: "info" | "error" = "info") => {
    setHint({ msg, kind });
    setTimeout(() => setHint(null), 4000);
  };

  const selectedJournal = journals.find(j => j.id === selectedId) ?? null;

  // ── Journal actions ──────────────────────────────────────────────────────────

  const selectJournal = useCallback((journal: Journal) => {
    setSelectedId(journal.id);
    const existing = journalStates[journal.id];
    if (!existing || existing.toc.length === 0) {
      loadTocForId(journal.id, existing?.scope ?? 1);
    }
  }, [journalStates, loadTocForId]);

  const toggleFollow = async (journal: Journal, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (followingId) return;
    setFollowingId(journal.id);
    try {
      if (journal.is_following) {
        await api.unfollowJournal(journal.id);
        setJournals(prev => prev.map(j => j.id === journal.id ? { ...j, is_following: false } : j));
        setJournalOrder(prev => { const next = prev.filter(id => id !== journal.id); saveOrder(next); return next; });
        if (selectedId === journal.id) setSelectedId(null);
        showHint(`Unfollowed ${journal.abbreviation}`);
      } else {
        await api.followJournal(journal.id);
        setJournals(prev => prev.map(j => j.id === journal.id ? { ...j, is_following: true } : j));
        setJournalOrder(prev => {
          if (prev.includes(journal.id)) return prev;
          const next = [...prev, journal.id]; saveOrder(next); return next;
        });
        selectJournal({ ...journal, is_following: true });
        showHint(`Now following ${journal.abbreviation}`);
      }
    } catch {
      showHint("Could not update follow status — please try again.", "error");
    } finally {
      setFollowingId(null);
    }
  };

  const moveJournal = (id: string, dir: "up" | "down") => {
    setJournalOrder(prev => {
      const idx = prev.indexOf(id);
      if (idx === -1) return prev;
      const next = [...prev];
      if (dir === "up" && idx > 0) [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      else if (dir === "down" && idx < next.length - 1) [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
      saveOrder(next);
      return next;
    });
  };

  // ── Article actions ───────────────────────────────────────────────────────────

  const handleDownload = async (article: TocArticle) => {
    const input = article.pmid ? `pmid:${article.pmid}` : article.doi ?? article.url;
    try {
      await api.enqueue(input);
      api.addHistory({
        pmid: article.pmid || null, doi: article.doi, title: article.title,
        authors: article.authors, journal: article.journal, pub_date: article.pub_date,
        abstract: article.abstract, url: article.url,
      }).catch(() => {});
      refreshQueue();
      showHint(isDesktop ? "Added to download queue" : "Sent to desktop for download");
    } catch {
      showHint(isDesktop ? "Could not queue download — please try again." : "Could not send to desktop — please try again.", "error");
    }
  };

  const handleCancelDownload = async (article: TocArticle) => {
    const item = matchQueue(article, queueRef.current);
    if (item && item.status === "queued") { await api.deleteQueueItem(item.id); refreshQueue(); }
  };

  const toggleEmail = (article: TocArticle) => {
    const key = article.pmid ?? article.doi ?? article.url;
    setEmailSet(prev => { const s = new Set(prev); s.has(key) ? s.delete(key) : s.add(key); return s; });
  };

  // Flatten all loaded TOCs so a key in emailSet can be resolved to an article
  // even when the user has navigated away from the journal it came from.
  const flatArticleByKey = (() => {
    const m = new Map<string, TocArticle>();
    Object.values(journalStates).forEach(state => {
      state.toc.forEach(a => {
        const k = a.pmid ?? a.doi ?? a.url;
        if (!m.has(k)) m.set(k, a);
      });
    });
    return m;
  })();

  const splitSelection = (dlMap: Record<string, string>) => {
    const readyIds: string[] = [];
    const toQueue: TocArticle[] = [];
    const pendingPmids: string[] = [];
    emailSet.forEach(key => {
      const article = flatArticleByKey.get(key);
      if (!article) return;
      const dbId = article.pmid ? dlMap[article.pmid] : undefined;
      if (dbId) readyIds.push(dbId);
      else {
        toQueue.push(article);
        if (article.pmid) pendingPmids.push(article.pmid);
      }
    });
    return { readyIds, toQueue, pendingPmids };
  };

  const handleSendReadyOnly = async () => {
    if (emailSending || emailSet.size === 0) return;
    setEmailSending(true);
    try {
      const dl = await refreshDownloadedMap();
      const { readyIds } = splitSelection(dl);
      if (readyIds.length === 0) { showHint("No selected articles are downloaded yet.", "error"); return; }
      await api.emailArticles(readyIds);
      showHint(`Sent ${readyIds.length} article${readyIds.length > 1 ? "s" : ""} to your email ✓`);
      setEmailSet(prev => {
        const next = new Set(prev);
        readyIds.forEach(id => {
          for (const [k, a] of flatArticleByKey) if (a.pmid && dl[a.pmid] === id) next.delete(k);
        });
        return next;
      });
    } catch { showHint("Could not send email — check email settings.", "error"); }
    finally { setEmailSending(false); }
  };

  const handleSendEmails = async () => {
    if (emailSending || emailSet.size === 0) return;
    setEmailSending(true);
    try {
      const dl = await refreshDownloadedMap();
      const { readyIds, toQueue, pendingPmids } = splitSelection(dl);
      if (readyIds.length > 0) {
        await api.emailArticles(readyIds);
        showHint(`Sent ${readyIds.length} article${readyIds.length > 1 ? "s" : ""} to your email ✓`);
      }
      for (const a of toQueue) await handleDownload(a);
      if (toQueue.length > 0) {
        if (pendingPmids.length > 0) {
          const existing = loadPendingBatch();
          const merged = Array.from(new Set([...(existing?.pmids ?? []), ...pendingPmids]));
          savePendingBatch({ pmids: merged, queuedAt: Date.now() });
        }
        showHint(`${toQueue.length} article(s) queued — email will go out automatically when downloads finish.`);
      }
      setEmailSet(new Set());
    } catch { showHint("Could not send email — check email settings.", "error"); }
    finally { setEmailSending(false); }
  };

  const handleReport = async (article: TocArticle) => {
    const item = matchQueue(article, queueRef.current);
    if (!item) return;
    try {
      await api.reportFailure(item.id);
      showHint("Report sent");
    } catch {
      showHint("Could not send report — item may have been removed.", "error");
    }
  };

  const getStatus = (article: TocArticle): DlStatus => {
    const item = matchQueue(article, queue);
    if (!item) return "idle";
    if (item.status === "queued") return "queued";
    if (item.status === "claimed" || item.status === "downloading") return "downloading";
    if (item.status === "done") return "done";
    if (item.status === "failed") return "failed";
    return "idle";
  };

  const getQueuePos = (article: TocArticle): number => {
    const active = queue.filter(q => q.status === "queued" || q.status === "claimed" || q.status === "downloading");
    const idx = active.findIndex(q =>
      (article.pmid && q.input.includes(article.pmid)) ||
      (article.doi && q.input.toLowerCase().includes(article.doi.toLowerCase())) ||
      q.input === article.url
    );
    return idx === -1 ? 0 : idx + 1;
  };

  const handleAddJournal = async () => {
    if (!addName.trim()) return;
    setAddLoading(true);
    try {
      const j = await api.addCustomJournal(addName.trim(), addAbbr.trim(), addIssn.trim());
      setJournals(prev => [...prev, j]);
      setAddName(""); setAddAbbr(""); setAddIssn(""); setShowAddForm(false);
      showHint(`Added "${j.full_name}"`);
    } catch { showHint("Could not add journal.", "error"); }
    finally { setAddLoading(false); }
  };

  // ── Derived data ──────────────────────────────────────────────────────────────

  const sl = search.toLowerCase();
  const followed = journals.filter(j => j.is_following);
  const sortedFollowed = [...followed].sort((a, b) => {
    const ai = journalOrder.indexOf(a.id);
    const bi = journalOrder.indexOf(b.id);
    if (ai === -1 && bi === -1) return 0;
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
  const filteredFollowed = sl ? sortedFollowed.filter(j =>
    j.full_name.toLowerCase().includes(sl) || j.abbreviation.toLowerCase().includes(sl)
  ) : sortedFollowed;

  const discoverResults = sl ? journals.filter(j =>
    !j.is_following && (j.full_name.toLowerCase().includes(sl) || j.abbreviation.toLowerCase().includes(sl))
  ).slice(0, 6) : [];

  const currentState = selectedId ? journalStates[selectedId] : null;
  const currentToc = currentState?.toc ?? [];
  const currentLoading = currentState?.loading ?? false;
  const currentScope = currentState?.scope ?? 1;

  const typeOf = (a: TocArticle) => a.article_type ?? "Other";
  const typeCounts = currentToc.reduce<Record<string, number>>((acc, a) => {
    const t = typeOf(a); acc[t] = (acc[t] ?? 0) + 1; return acc;
  }, {});
  const availableTypes = Object.keys(typeCounts).sort();
  const excludedTypes = (selectedId && journalStates[selectedId]?.excludedTypes) || new Set<string>();

  // Subspecialty classification — articles can belong to multiple subspecialties
  // (e.g. "ovarian cancer in pregnancy" → Onco-gynecology + Obstetrics).
  const subspecialtyByKey = (() => {
    const m = new Map<string, Set<Subspecialty>>();
    currentToc.forEach(a => {
      const k = a.pmid ?? a.doi ?? a.url ?? a.title;
      m.set(k, classifySubspecialty(a));
    });
    return m;
  })();
  const subspecsOf = (a: TocArticle): Set<Subspecialty> =>
    subspecialtyByKey.get(a.pmid ?? a.doi ?? a.url ?? a.title) ?? new Set(["Other"]);

  const subspecCounts = currentToc.reduce<Record<string, number>>((acc, a) => {
    subspecsOf(a).forEach(s => { acc[s] = (acc[s] ?? 0) + 1; });
    return acc;
  }, {});
  const availableSubspecs = SUBSPECIALTY_ORDER.filter(s => (subspecCounts[s] ?? 0) > 0);
  const excludedSubspecs = (selectedId && journalStates[selectedId]?.excludedSubspecialties) || new Set<Subspecialty>();

  // Show article if at least one of its subspecialties is NOT excluded.
  const filteredToc = currentToc.filter(a => {
    if (excludedTypes.has(typeOf(a))) return false;
    const labels = subspecsOf(a);
    for (const s of labels) if (!excludedSubspecs.has(s)) return true;
    return false;
  });

  const toggleType = (t: string) => {
    if (!selectedId) return;
    setJournalStates(prev => {
      const cur = prev[selectedId];
      if (!cur) return prev;
      const next = new Set(cur.excludedTypes ?? []);
      if (next.has(t)) next.delete(t); else next.add(t);
      return { ...prev, [selectedId]: { ...cur, excludedTypes: next } };
    });
  };

  const toggleSubspec = (s: Subspecialty) => {
    if (!selectedId) return;
    setJournalStates(prev => {
      const cur = prev[selectedId];
      if (!cur) return prev;
      const next = new Set(cur.excludedSubspecialties ?? []);
      if (next.has(s)) next.delete(s); else next.add(s);
      return { ...prev, [selectedId]: { ...cur, excludedSubspecialties: next } };
    });
  };

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>

      {/* ─── Left journal panel ─────────────────────────────── */}
      <div style={S.leftPanel}>

        {/* Header + search */}
        <div style={{ padding: "1rem 1rem 0.5rem", flexShrink: 0 }}>
          <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 700, fontSize: "0.95rem", color: "var(--color-text-primary, #1A2332)", marginBottom: "0.625rem" }}>
            Journals
          </div>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search journals…"
            style={S.searchInput}
          />
        </div>

        {hint && <div style={{ ...S.hint(hint.kind), margin: "0 1rem 0.5rem" }}>{hint.msg}</div>}

        {/* Journal list */}
        <div style={{ flex: 1, overflowY: "auto" }}>

          {/* My Journals */}
          {filteredFollowed.length > 0 && (
            <>
              <div style={S.sectionLabel}>My Journals</div>
              {filteredFollowed.map((j, idx) => (
                <JournalListItem
                  key={j.id}
                  journal={j}
                  isSelected={selectedId === j.id}
                  isLoading={followingId === j.id}
                  showReorder={!sl}
                  canMoveUp={idx > 0}
                  canMoveDown={idx < filteredFollowed.length - 1}
                  onSelect={() => selectJournal(j)}
                  onToggleFollow={e => toggleFollow(j, e)}
                  onMoveUp={() => moveJournal(j.id, "up")}
                  onMoveDown={() => moveJournal(j.id, "down")}
                />
              ))}
            </>
          )}

          {/* Discover (only when searching) */}
          {discoverResults.length > 0 && (
            <>
              <div style={{ ...S.sectionLabel, marginTop: filteredFollowed.length ? "0.875rem" : 0 }}>
                Discover
              </div>
              {discoverResults.map(j => (
                <JournalListItem
                  key={j.id}
                  journal={j}
                  isSelected={selectedId === j.id}
                  isLoading={followingId === j.id}
                  showReorder={false}
                  canMoveUp={false}
                  canMoveDown={false}
                  onSelect={() => selectJournal(j)}
                  onToggleFollow={e => toggleFollow(j, e)}
                  onMoveUp={() => {}}
                  onMoveDown={() => {}}
                />
              ))}
            </>
          )}

          {sl && filteredFollowed.length === 0 && discoverResults.length === 0 && (
            <div style={{ padding: "1.25rem 1rem", fontSize: "0.8rem", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Sans', sans-serif" }}>
              No journals match "{search}"
            </div>
          )}

          {!sl && followed.length === 0 && (
            <div style={{ padding: "1.25rem 1rem", fontSize: "0.8rem", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Sans', sans-serif", lineHeight: 1.5 }}>
              Search to find and follow journals from our list, or add one by URL below.
            </div>
          )}
        </div>

        {/* Add by URL/ISSN */}
        <div style={{ borderTop: "1px solid var(--color-border-light, #EDE6DA)", padding: "0.75rem 1rem", flexShrink: 0 }}>
          {!showAddForm ? (
            <button onClick={() => setShowAddForm(true)} style={S.addBtn}>
              + Add by URL / ISSN
            </button>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              <input value={addName} onChange={e => setAddName(e.target.value)} placeholder="Journal name *" style={S.miniInput} />
              <input value={addAbbr} onChange={e => setAddAbbr(e.target.value)} placeholder="Abbreviation" style={S.miniInput} />
              <input value={addIssn} onChange={e => setAddIssn(e.target.value)} placeholder="ISSN or homepage URL" style={S.miniInput} />
              <div style={{ display: "flex", gap: "0.375rem", marginTop: "0.125rem" }}>
                <button onClick={handleAddJournal} disabled={!addName.trim() || addLoading}
                  style={{ flex: 1, padding: "0.35rem", border: "none", borderRadius: "0.25rem", background: "var(--color-accent, #C0783A)", color: "#fff", fontFamily: "'DM Sans', sans-serif", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer", opacity: addLoading || !addName.trim() ? 0.6 : 1 }}>
                  {addLoading ? "Adding…" : "Add"}
                </button>
                <button onClick={() => { setShowAddForm(false); setAddName(""); setAddAbbr(""); setAddIssn(""); }}
                  style={{ padding: "0.35rem 0.6rem", border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.25rem", background: "none", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Sans', sans-serif", fontSize: "0.78rem", cursor: "pointer" }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── Right article panel ─────────────────────────────── */}
      <div style={S.rightPanel}>
        {!selectedJournal ? (
          <div style={S.emptyState}>
            <div style={{ fontSize: "2.5rem", opacity: 0.2, marginBottom: "1rem" }}>◎</div>
            <div style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: "1.2rem", color: "var(--color-text-primary, #1A2332)", marginBottom: "0.5rem" }}>
              Select a journal
            </div>
            <div style={{ fontSize: "0.825rem", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Sans', sans-serif", maxWidth: 280, textAlign: "center" as const }}>
              Choose a journal from the left panel, or search to discover and follow new ones
            </div>
          </div>
        ) : (
          <>
            {/* Journal header */}
            <div style={S.journalHeader}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h2 style={S.journalTitle}>{selectedJournal.full_name}</h2>
                <div style={{ fontSize: "0.75rem", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Mono', monospace", marginTop: "0.2rem" }}>
                  {selectedJournal.abbreviation}
                  {selectedJournal.category === "obgyn" && " · OB/GYN"}
                  {selectedJournal.category === "general" && " · General Medicine"}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexShrink: 0 }}>
                {emailSet.size > 0 && (
                  <>
                    <button
                      onClick={handleSendReadyOnly}
                      disabled={emailSending}
                      style={{ ...S.emailSendBtn, background: "transparent", color: "var(--color-accent, #C0783A)", border: "1px solid var(--color-accent, #C0783A)" }}
                      title="Email only the articles already downloaded — skip queueing missing ones"
                    >
                      Send ready only
                    </button>
                    <button onClick={handleSendEmails} disabled={emailSending} style={S.emailSendBtn}>
                      {emailSending ? "Sending…" : `✉ Send ${emailSet.size}`}
                    </button>
                  </>
                )}
                <button
                  onClick={() => loadTocForId(selectedJournal.id, currentScope)}
                  disabled={currentLoading}
                  style={S.refreshBtn(currentLoading)}
                  title="Refresh articles"
                >
                  {currentLoading ? "…" : "↺ Refresh"}
                </button>
              </div>
            </div>

            {/* Scope pills */}
            <div style={{ display: "flex", gap: "0.375rem", padding: "0 2rem 0.5rem", flexWrap: "wrap" as const }}>
              {([1, 3, 6, 12] as Scope[]).map(s => (
                <button key={s} onClick={() => loadTocForId(selectedJournal.id, s)} style={S.scopePill(currentScope === s)}>
                  {SCOPE_LABELS[s]}
                </button>
              ))}
            </div>

            {/* Subspecialty filter chips */}
            {availableSubspecs.length > 1 && (
              <div style={{ display: "flex", gap: "0.375rem", padding: "0 2rem 0.5rem", flexWrap: "wrap" as const, alignItems: "center" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Mono', monospace", marginRight: "0.25rem" }}>Topic:</span>
                {availableSubspecs.map(s => {
                  const active = !excludedSubspecs.has(s);
                  return (
                    <button key={s} onClick={() => toggleSubspec(s)} style={S.scopePill(active)} title={active ? "Click to hide" : "Click to show"}>
                      {s} ({subspecCounts[s]})
                    </button>
                  );
                })}
              </div>
            )}

            {/* Article-type filter chips */}
            {availableTypes.length > 1 && (
              <div style={{ display: "flex", gap: "0.375rem", padding: "0 2rem 1.25rem", flexWrap: "wrap" as const }}>
                {availableTypes.map(t => {
                  const active = !excludedTypes.has(t);
                  return (
                    <button key={t} onClick={() => toggleType(t)} style={S.scopePill(active)} title={active ? "Click to hide" : "Click to show"}>
                      {t} ({typeCounts[t]})
                    </button>
                  );
                })}
              </div>
            )}

            {/* Articles */}
            <div style={{ padding: "0 2rem 4rem" }}>
              {currentLoading && <div style={S.infoMsg}>Loading articles…</div>}
              {!currentLoading && filteredToc.length === 0 && (
                <div style={S.infoMsg}>
                  {currentToc.length === 0
                    ? (selectedJournal.is_following
                        ? "No articles found for this period. Try a longer range."
                        : "Follow this journal to load articles.")
                    : "No articles match the selected filters."}
                </div>
              )}
              {!currentLoading && filteredToc.map(article => {
                const key = article.pmid ?? article.doi ?? article.url;
                return (
                  <ArticleItem
                    key={key}
                    article={article}
                    status={getStatus(article)}
                    queuePos={getQueuePos(article)}
                    emailSelected={emailSet.has(key)}
                    isDesktop={isDesktop}
                    onDownload={() => handleDownload(article)}
                    onCancel={() => handleCancelDownload(article)}
                    onEmail={() => toggleEmail(article)}
                    onReport={() => handleReport(article)}
                  />
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Journal list item ─────────────────────────────────────────────────────────

function JournalListItem({ journal, isSelected, isLoading, showReorder, canMoveUp, canMoveDown, onSelect, onToggleFollow, onMoveUp, onMoveDown }: {
  journal: Journal; isSelected: boolean; isLoading: boolean;
  showReorder: boolean; canMoveUp: boolean; canMoveDown: boolean;
  onSelect: () => void; onToggleFollow: (e: React.MouseEvent) => void;
  onMoveUp: () => void; onMoveDown: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex", alignItems: "center", gap: "0.375rem",
        padding: "0.45rem 0.75rem 0.45rem 1rem",
        cursor: "pointer",
        background: isSelected ? "var(--color-accent-light, #F0D4B4)" : "transparent",
        borderLeft: isSelected ? "3px solid var(--color-accent, #C0783A)" : "3px solid transparent",
        transition: "background 0.1s",
      }}
    >
      {/* Reorder arrows */}
      {showReorder && (
        <div style={{ display: "flex", flexDirection: "column", gap: 0, flexShrink: 0, opacity: 0.4 }}>
          <button onClick={e => { e.stopPropagation(); onMoveUp(); }}
            disabled={!canMoveUp}
            style={{ background: "none", border: "none", cursor: canMoveUp ? "pointer" : "default", padding: "0 2px", fontSize: "0.55rem", lineHeight: 1, color: "var(--color-text-secondary, #5A6475)", opacity: canMoveUp ? 1 : 0.3 }}>
            ▲
          </button>
          <button onClick={e => { e.stopPropagation(); onMoveDown(); }}
            disabled={!canMoveDown}
            style={{ background: "none", border: "none", cursor: canMoveDown ? "pointer" : "default", padding: "0 2px", fontSize: "0.55rem", lineHeight: 1, color: "var(--color-text-secondary, #5A6475)", opacity: canMoveDown ? 1 : 0.3 }}>
            ▼
          </button>
        </div>
      )}

      {/* Journal name */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: "'DM Sans', sans-serif", fontWeight: isSelected ? 600 : 400, fontSize: "0.82rem", color: isSelected ? "var(--color-accent-dim, #8A5228)" : "var(--color-text-primary, #1A2332)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {journal.abbreviation || journal.full_name}
        </div>
        {journal.abbreviation && journal.abbreviation !== journal.full_name && (
          <div style={{ fontSize: "0.68rem", color: "var(--color-text-secondary, #5A6475)", fontFamily: "'DM Sans', sans-serif", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {journal.full_name}
          </div>
        )}
      </div>

      {/* Follow toggle */}
      <button
        onClick={onToggleFollow}
        disabled={isLoading}
        title={journal.is_following ? "Unfollow" : "Follow"}
        style={{
          flexShrink: 0, padding: "0.15rem 0.45rem", borderRadius: "0.2rem",
          border: journal.is_following ? "1px solid var(--color-accent, #C0783A)" : "1px solid var(--color-border, #D8D0C4)",
          background: journal.is_following ? "var(--color-accent, #C0783A)" : "transparent",
          color: journal.is_following ? "#fff" : "var(--color-text-secondary, #5A6475)",
          fontFamily: "'DM Sans', sans-serif", fontSize: "0.68rem", fontWeight: 600,
          cursor: isLoading ? "default" : "pointer", opacity: isLoading ? 0.5 : 1,
        }}
      >
        {isLoading ? "…" : journal.is_following ? "✓" : "+"}
      </button>
    </div>
  );
}

// ─── Article item ──────────────────────────────────────────────────────────────

function ArticleItem({ article, status, queuePos, emailSelected, isDesktop, onDownload, onCancel, onEmail, onReport }: {
  article: TocArticle; status: DlStatus; queuePos: number; emailSelected: boolean; isDesktop: boolean;
  onDownload: () => void; onCancel: () => void; onEmail: () => void; onReport: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const dlLabel = () => {
    if (status === "queued") return isDesktop ? (queuePos > 1 ? `#${queuePos} queued` : "Queued…") : (queuePos > 1 ? `🖥 #${queuePos}` : "🖥 Sending…");
    if (status === "downloading") return isDesktop ? "Downloading…" : "🖥 Loading…";
    if (status === "done") return "View PDF";
    if (status === "failed") return "Failed";
    return isDesktop ? "Download" : "🖥 Send";
  };

  const dlColor = status === "done" ? "var(--color-success, #2E6B4F)"
    : status === "failed" ? "var(--color-error, #9B2C2C)"
    : status === "queued" || status === "downloading" ? "var(--color-text-secondary, #5A6475)"
    : "var(--color-accent, #C0783A)";

  const canAct = status === "idle" || status === "queued";

  return (
    <div style={{ borderBottom: "1px solid var(--color-border-light, #EDE6DA)", padding: "0.75rem 0" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            onClick={() => setExpanded(e => !e)}
            style={{ fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 600, fontSize: "0.9rem", color: "var(--color-text-primary, #1A2332)", cursor: "pointer", lineHeight: 1.45 }}
          >
            {article.title}
          </div>
          <div style={{ fontSize: "0.765rem", color: "var(--color-text-secondary, #5A6475)", marginTop: "0.2rem", fontFamily: "'DM Sans', sans-serif" }}>
            {article.authors.slice(0, 3).join(", ")}{article.authors.length > 3 ? " et al." : ""}
            {article.pub_date && <span style={{ marginLeft: "0.4rem", fontFamily: "'DM Mono', monospace", opacity: 0.8 }}>· {article.pub_date}</span>}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", flexShrink: 0 }}>
          <button
            onClick={onEmail}
            title={emailSelected ? "Remove from email list" : "Add to email list"}
            style={{
              background: emailSelected ? "var(--color-accent-light, #F0D4B4)" : "none",
              border: emailSelected ? "1px solid var(--color-accent, #C0783A)" : "1px solid var(--color-border, #D8D0C4)",
              borderRadius: "0.25rem", cursor: "pointer", padding: "0.25rem 0.45rem",
              color: emailSelected ? "var(--color-accent-dim, #8A5228)" : "var(--color-text-secondary, #5A6475)",
              fontSize: "0.8rem", lineHeight: 1,
            }}
          >
            ✉
          </button>
          {status === "failed" && (
            <button onClick={onReport} style={{ background: "none", border: "1px solid var(--color-error, #9B2C2C)", borderRadius: "0.25rem", cursor: "pointer", padding: "0.25rem 0.45rem", color: "var(--color-error, #9B2C2C)", fontSize: "0.72rem", fontFamily: "'DM Sans', sans-serif" }}>
              Report
            </button>
          )}
          <button
            onClick={canAct ? (status === "idle" ? onDownload : onCancel) : undefined}
            disabled={status === "downloading" || status === "done"}
            style={{
              padding: "0.28rem 0.65rem", borderRadius: "0.25rem",
              border: `1px solid ${dlColor}`,
              background: status === "done" ? "var(--color-success-bg, #D4EDE2)" : status === "failed" ? "var(--color-error-bg, #F7DCDC)" : "transparent",
              color: dlColor, cursor: canAct ? "pointer" : "default",
              fontSize: "0.77rem", fontFamily: "'DM Sans', sans-serif", fontWeight: 500,
              minWidth: 74, textAlign: "center" as const,
              opacity: status === "downloading" || status === "done" ? 0.85 : 1,
              transition: "all 0.12s",
            }}
          >
            {dlLabel()}
          </button>
        </div>
      </div>
      {expanded && (
        <div style={{ marginTop: "0.6rem", fontSize: "0.82rem", lineHeight: 1.65, color: "var(--color-text-primary, #1A2332)", fontFamily: "'Lora', Georgia, serif", background: "var(--color-bg, #F5F0E8)", borderRadius: "0.25rem", padding: "0.75rem 1rem", borderLeft: "3px solid var(--color-accent, #C0783A)" }}>
          {article.abstract
            ? article.abstract
            : <span style={{ fontStyle: "italic", opacity: 0.7 }}>No abstract available.</span>}
        </div>
      )}
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const S = {
  leftPanel: {
    width: 252, minWidth: 252, flexShrink: 0,
    display: "flex", flexDirection: "column" as const,
    borderRight: "1px solid var(--color-border, #D8D0C4)",
    background: "var(--color-bg-card, #FDFAF4)",
    height: "100vh", overflow: "hidden",
  } as CSSProperties,

  rightPanel: {
    flex: 1, minWidth: 0, overflowY: "auto" as const, height: "100vh",
    background: "var(--color-bg, #F5F0E8)",
  } as CSSProperties,

  searchInput: {
    width: "100%", boxSizing: "border-box" as const,
    padding: "0.45rem 0.75rem",
    border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.25rem",
    fontFamily: "'DM Sans', sans-serif", fontSize: "0.82rem",
    background: "var(--color-bg, #F5F0E8)", color: "var(--color-text-primary, #1A2332)",
    outline: "none",
  } as CSSProperties,

  sectionLabel: {
    padding: "0.4rem 1rem 0.25rem",
    fontFamily: "'DM Sans', sans-serif", fontWeight: 700, fontSize: "0.65rem",
    textTransform: "uppercase" as const, letterSpacing: "0.08em",
    color: "var(--color-text-secondary, #5A6475)",
  } as CSSProperties,

  addBtn: {
    width: "100%", padding: "0.45rem 0.75rem",
    border: "1px dashed var(--color-border, #D8D0C4)", borderRadius: "0.25rem",
    background: "none", color: "var(--color-text-secondary, #5A6475)",
    fontFamily: "'DM Sans', sans-serif", fontSize: "0.78rem", cursor: "pointer",
    textAlign: "left" as const,
  } as CSSProperties,

  miniInput: {
    width: "100%", boxSizing: "border-box" as const,
    padding: "0.35rem 0.5rem",
    border: "1px solid var(--color-border, #D8D0C4)", borderRadius: "0.2rem",
    fontFamily: "'DM Sans', sans-serif", fontSize: "0.78rem",
    background: "var(--color-bg, #F5F0E8)", color: "var(--color-text-primary, #1A2332)",
    outline: "none",
  } as CSSProperties,

  hint: (kind: "info" | "error") => ({
    padding: "0.45rem 0.75rem", borderRadius: "0.25rem",
    fontSize: "0.775rem", fontFamily: "'DM Sans', sans-serif", lineHeight: 1.4,
    background: kind === "error" ? "var(--color-error-bg, #F7DCDC)" : "var(--color-accent-light, #F0D4B4)",
    color: kind === "error" ? "var(--color-error, #9B2C2C)" : "var(--color-accent-dim, #8A5228)",
  } as CSSProperties),

  journalHeader: {
    display: "flex", alignItems: "flex-start", gap: "1rem",
    padding: "1.75rem 2rem 0.75rem",
    borderBottom: "1px solid var(--color-border-light, #EDE6DA)",
    marginBottom: "1rem",
    background: "var(--color-bg-card, #FDFAF4)",
  } as CSSProperties,

  journalTitle: {
    fontFamily: "'Playfair Display', Georgia, serif", fontWeight: 700, fontSize: "1.35rem",
    margin: 0, color: "var(--color-text-primary, #1A2332)", lineHeight: 1.25,
  } as CSSProperties,

  followBtn: (following: boolean, loading: boolean) => ({
    padding: "0.35rem 1rem", borderRadius: "0.25rem", cursor: loading ? "default" : "pointer",
    border: following ? "1px solid var(--color-accent, #C0783A)" : "1px solid var(--color-border, #D8D0C4)",
    background: following ? "var(--color-accent-light, #F0D4B4)" : "transparent",
    color: following ? "var(--color-accent-dim, #8A5228)" : "var(--color-text-secondary, #5A6475)",
    fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: "0.8rem",
    opacity: loading ? 0.6 : 1, transition: "all 0.15s",
  } as CSSProperties),

  emailSendBtn: {
    padding: "0.35rem 0.875rem", borderRadius: "0.25rem",
    border: "1px solid var(--color-accent, #C0783A)",
    background: "var(--color-accent, #C0783A)", color: "#fff",
    fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: "0.8rem", cursor: "pointer",
  } as CSSProperties,

  refreshBtn: (loading: boolean) => ({
    padding: "0.35rem 0.875rem", borderRadius: "0.25rem", cursor: loading ? "default" : "pointer",
    border: "1px solid var(--color-border, #D8D0C4)",
    background: "transparent",
    color: "var(--color-text-secondary, #5A6475)",
    fontFamily: "'DM Sans', sans-serif", fontWeight: 500, fontSize: "0.8rem",
    opacity: loading ? 0.5 : 1, transition: "opacity 0.15s",
  } as CSSProperties),

  scopePill: (active: boolean) => ({
    padding: "0.22rem 0.75rem", borderRadius: "1rem",
    border: "1px solid var(--color-border, #D8D0C4)",
    background: active ? "var(--color-accent, #C0783A)" : "var(--color-bg-card, #FDFAF4)",
    color: active ? "#fff" : "var(--color-text-secondary, #5A6475)",
    cursor: "pointer", fontSize: "0.75rem",
    fontFamily: "'DM Sans', sans-serif", fontWeight: 500, transition: "all 0.15s",
  } as CSSProperties),

  emptyState: {
    display: "flex", flexDirection: "column" as const, alignItems: "center", justifyContent: "center",
    height: "100%", padding: "3rem",
  } as CSSProperties,

  infoMsg: {
    color: "var(--color-text-secondary, #5A6475)", fontSize: "0.875rem",
    fontFamily: "'DM Sans', sans-serif", padding: "2rem 0",
  } as CSSProperties,
};
