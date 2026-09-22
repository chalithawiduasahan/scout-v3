import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  BarChart3,
  ChevronDown,
  Clock,
  Eye,
  EyeOff,
  Globe,
  History,
  Home,
  Image as ImageIcon,
  Key,
  Loader2,
  LogOut,
  Mail,
  MapPin,
  Menu,
  Minus,
  Plus,
  Target,
  X,
  Zap,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';


const SCALE_OPTIONS = [
  { value: 'small', label: 'Small (<10 staff)' },
  { value: 'medium', label: 'Medium (10-50 staff)' },
  { value: 'large', label: 'Large (50+ staff)' },
];

const DOGFOOD_NICHE =
  'automation freelancers and automation agencies';


function ScaleSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (
        wrapRef.current &&
        !wrapRef.current.contains(
          event.target as Node
        )
      ) {
        setOpen(false);
      }
    };

    document.addEventListener(
      'mousedown',
      handleClick
    );

    return () =>
      document.removeEventListener(
        'mousedown',
        handleClick
      );
  }, []);

  const selected =
    SCALE_OPTIONS.find(
      (option) => option.value === value
    ) || SCALE_OPTIONS[0];

  return (
    <div
      ref={wrapRef}
      className="relative"
    >
      <button
        type="button"
        onClick={() =>
          setOpen((current) => !current)
        }
        className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-left text-sm text-white focus:border-scout-400 focus:outline-none"
      >
        <span>
          {selected.label}
        </span>

        <ChevronDown
          className={`h-4 w-4 shrink-0 text-ink-400 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 overflow-hidden rounded-xl border border-white/10 bg-ink-900 shadow-2xl">
          {SCALE_OPTIONS.map(
            (option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(
                    option.value
                  );
                  setOpen(false);
                }}
                className={`block w-full px-4 py-2.5 text-left text-sm transition-colors ${
                  option.value === value
                    ? 'bg-scout-400/20 text-scout-400'
                    : 'text-ink-200 hover:bg-white/5 hover:text-white'
                }`}
              >
                {option.label}
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}


function CountSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const current =
    parseInt(value, 10) || 1;

  return (
    <div className="flex h-[42px] items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white">
      <span className="px-2 font-medium">
        {current} lead
        {current > 1 ? 's' : ''}
      </span>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() =>
            onChange(
              String(
                Math.max(
                  current - 1,
                  1
                )
              )
            )
          }
          disabled={current <= 1}
          className="rounded-lg p-1 text-ink-400 hover:bg-white/10 hover:text-white disabled:opacity-30"
        >
          <Minus className="h-4 w-4" />
        </button>

        <button
          type="button"
          onClick={() =>
            onChange(
              String(
                Math.min(
                  current + 1,
                  5
                )
              )
            )
          }
          disabled={current >= 5}
          className="rounded-lg p-1 text-ink-400 hover:bg-white/10 hover:text-white disabled:opacity-30"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}


type CampaignType =
  | 'normal'
  | 'dogfood';


type Note = {
  msg: string;
  type: 'success' | 'error';
} | null;


export default function Dashboard() {
  const {
    session,
    signOut,
  } = useAuth();

  const displayName =
    session?.user.user_metadata?.full_name ||
    session?.user.email?.split('@')[0] ||
    'there';

  const authHeaders: Record<
    string,
    string
  > =
    session?.access_token
      ? {
          Authorization:
            `Bearer ${session.access_token}`,
        }
      : {};

  const API_BASE =
    import.meta.env.VITE_BACKEND_URL ||
    'https://scout-v3.onrender.com';

  const [activeTab, setActiveTab] =
    useState<
      'home' | 'history' | 'analytics'
    >('home');

  const [
    sidebarOpen,
    setSidebarOpen,
  ] = useState(true);

  const [
    founderAccess,
    setFounderAccess,
  ] = useState(false);

  const [
    campaignType,
    setCampaignType,
  ] = useState<CampaignType>(
    'normal'
  );

  const [niche, setNiche] =
    useState('');

  const [location, setLocation] =
    useState('');

  const [scale, setScale] =
    useState('small');

  const [count, setCount] =
    useState('1');

  const [gmailAddress, setGmailAddress] =
    useState(
      () =>
        localStorage.getItem(
          'scout_gmail_address'
        ) || ''
    );

  const [
    gmailAppPassword,
    setGmailAppPassword,
  ] = useState(
    () =>
      localStorage.getItem(
        'scout_gmail_app_password'
      ) || ''
  );

  const [
    showPassword,
    setShowPassword,
  ] = useState(false);

  const [
    mailboxSaving,
    setMailboxSaving,
  ] = useState(false);

  const [
    mailboxConnected,
    setMailboxConnected,
  ] = useState(false);

  const [
    mailboxNote,
    setMailboxNote,
  ] = useState<Note>(null);

  const [status, setStatus] =
    useState('');

  const [error, setError] =
    useState('');

  const [loading, setLoading] =
    useState(false);

  const [
    resultsQueue,
    setResultsQueue,
  ] = useState<any[]>([]);

  const [
    currentIndex,
    setCurrentIndex,
  ] = useState(0);

  const [
    recipientEmail,
    setRecipientEmail,
  ] = useState('');

  const [subject, setSubject] =
    useState('');

  const [body, setBody] =
    useState('');

  const [
    sendLoading,
    setSendLoading,
  ] = useState(false);

  const [
    sendNote,
    setSendNote,
  ] = useState<Note>(null);

  const [
    historyItems,
    setHistoryItems,
  ] = useState<any[]>([]);

  const [
    selectedHistoryItem,
    setSelectedHistoryItem,
  ] = useState<any>(null);

  const [lightbox, setLightbox] =
    useState<{
      url: string;
      cap: string;
    } | null>(null);


  const getImageUrl = (
    path: string
  ) => {
    if (!path) {
      return '';
    }

    if (
      path.startsWith(
        'http://'
      ) ||
      path.startsWith(
        'https://'
      )
    ) {
      return path;
    }

    return `${API_BASE}/${path.replace(
      /^\//,
      ''
    )}`;
  };


  const finalizeSignature = (
    text: string,
    name: string,
    type: CampaignType
  ) => {
    const stripped =
      String(text || '')
        .replace(
          /\n*\s*(Best regards|Warm regards|Regards|Sincerely|Thanks|Cheers)[,.]?\s*[\s\S]*$/i,
          ''
        )
        .trim();

    if (
      type === 'dogfood'
    ) {
      return (
        stripped +
        '\n\nBest regards,\n' +
        name +
        '\nCEO & Founder, Scout'
      );
    }

    return (
      stripped +
      '\n\nBest regards,\n' +
      name
    );
  };


  const extractEmail = (
    text: string
  ) => {
    const match =
      String(text || '').match(
        /[\w.+-]+@[\w-]+\.[\w.-]+/
      );

    return match
      ? match[0]
      : '';
  };


  const loadQueueItem = (
    item: any
  ) => {
    if (!item) {
      return;
    }

    const finalRecipient =
      item.recipient_email ||
      item.contact_email ||
      item.website_email ||
      extractEmail(
        item.research_profile || ''
      );

    setRecipientEmail(
      finalRecipient
    );

    setSubject(
      item.draft_subject || ''
    );

    setBody(
      finalizeSignature(
        item.draft_body || '',
        displayName,
        item.campaign_type ===
          'dogfood'
          ? 'dogfood'
          : 'normal'
      )
    );

    setSendNote(null);
  };


  const fetchHistory =
    async () => {
      try {
        const response =
          await fetch(
            `${API_BASE}/api/history`,
            {
              headers: authHeaders,
            }
          );

        const data =
          await response.json();

        if (response.ok) {
          setHistoryItems(
            data.data || []
          );
        }
      } catch (fetchError) {
        console.error(
          'Failed to load history',
          fetchError
        );
      }
    };


  const checkMailboxStatus =
    async () => {
      try {
        const response =
          await fetch(
            `${API_BASE}/api/settings/mailbox`,
            {
              headers: authHeaders,
            }
          );

        const data =
          await response.json();

        setMailboxConnected(
          !!data.connected
        );
      } catch {
        // Keep the dashboard usable when settings are unavailable.
      }
    };


  const fetchFounderAccess =
    async () => {
      try {
        const response =
          await fetch(
            `${API_BASE}/api/founder-access`,
            {
              headers: authHeaders,
            }
          );

        if (!response.ok) {
          setFounderAccess(false);
          return;
        }

        const data =
          await response.json();

        setFounderAccess(
          !!data.allowed
        );

        if (
          !data.allowed &&
          campaignType ===
            'dogfood'
        ) {
          setCampaignType(
            'normal'
          );
          setNiche('');
        }
      } catch {
        setFounderAccess(false);
      }
    };


  useEffect(() => {
    if (!session?.user.id) {
      return;
    }

    fetchHistory();
    checkMailboxStatus();
    fetchFounderAccess();
  }, [
    session?.user.id,
  ]);


  const handleGmailAddressChange =
    (value: string) => {
      setGmailAddress(value);

      localStorage.setItem(
        'scout_gmail_address',
        value
      );
    };


  const handleGmailPasswordChange =
    (value: string) => {
      setGmailAppPassword(value);

      localStorage.setItem(
        'scout_gmail_app_password',
        value
      );
    };


  const saveMailboxSettings =
    async () => {
      if (
        !gmailAddress ||
        !gmailAppPassword
      ) {
        setMailboxNote({
          msg:
            'Enter both your Gmail address and App Password first.',
          type: 'error',
        });

        return;
      }

      setMailboxSaving(true);
      setMailboxNote(null);

      try {
        const response =
          await fetch(
            `${API_BASE}/api/settings/mailbox`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
                ...authHeaders,
              },
              body: JSON.stringify({
                gmail_address:
                  gmailAddress,
                gmail_app_password:
                  gmailAppPassword,
              }),
            }
          );

        const data =
          await response.json();

        if (!response.ok) {
          setMailboxConnected(
            false
          );

          setMailboxNote({
            msg:
              data.detail ||
              'Could not connect mailbox.',
            type: 'error',
          });

          return;
        }

        setMailboxConnected(
          true
        );

        setMailboxNote({
          msg:
            data.message ||
            'Mailbox connected.',
          type: 'success',
        });
      } catch (sendError: any) {
        setMailboxNote({
          msg:
            sendError.message ||
            'Mailbox connection failed.',
          type: 'error',
        });
      } finally {
        setMailboxSaving(false);
      }
    };


  const changeCampaign = (
    nextType: CampaignType
  ) => {
    setCampaignType(
      nextType
    );
    setResultsQueue([]);
    setCurrentIndex(0);
    setError('');
    setSendNote(null);

    if (
      nextType ===
      'dogfood'
    ) {
      setNiche(
        DOGFOOD_NICHE
      );
    } else {
      setNiche('');
    }
  };


  const runScout =
    async () => {
      const effectiveNiche =
        campaignType ===
        'dogfood'
          ? DOGFOOD_NICHE
          : niche.trim();

      if (
        !effectiveNiche ||
        !location.trim()
      ) {
        setError(
          'Enter a location before running Scout.'
        );
        return;
      }

      setError('');
      setSendNote(null);
      setResultsQueue([]);
      setCurrentIndex(0);
      setLoading(true);

      const numRuns =
        parseInt(
          count,
          10
        ) || 1;

      const messages =
        campaignType ===
        'dogfood'
          ? [
              'Finding automation freelancers and agencies...',
              'Researching each prospect...',
              'Enriching the best contact...',
              'Preparing the Scout product proof...',
              'Drafting the personalized Scout pitch...',
            ]
          : [
              'Discovering random target businesses...',
              'Researching business facts & automation opportunities...',
              'Enriching the best contact...',
              'Capturing CRM, Email & Slack alert proofs...',
              'Drafting high-converting pitches...',
            ];

      let step = 0;

      setStatus(
        messages[0]
      );

      const timer =
        window.setInterval(
          () => {
            step += 1;

            if (
              step <
              messages.length
            ) {
              setStatus(
                messages[step]
              );
            }
          },
          5000
        );

      try {
        const response =
          await fetch(
            `${API_BASE}/api/start-agent`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
                ...authHeaders,
              },
              body: JSON.stringify({
                niche:
                  effectiveNiche,
                location,
                scale,
                count:
                  numRuns,
                campaign_type:
                  campaignType,
              }),
            }
          );

        const data =
          await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail ||
            'Something went wrong running Scout.'
          );
        }

        const queue =
          data.data || [];

        setResultsQueue(
          queue
        );

        if (
          queue.length
        ) {
          loadQueueItem(
            queue[0]
          );
        }
      } catch (runError: any) {
        setError(
          runError.message ||
          'Scout failed to run.'
        );
      } finally {
        window.clearInterval(
          timer
        );
        setLoading(false);
      }
    };


  const regenerateOutreach =
    async () => {
      const currentItem =
        resultsQueue[
          currentIndex
        ];

      if (!currentItem) {
        return;
      }

      try {
        const response =
          await fetch(
            `${API_BASE}/api/regenerate-outreach`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
                ...authHeaders,
              },
              body: JSON.stringify({
                business_name:
                  currentItem.business_name,
                research_profile:
                  currentItem.research_profile,
                campaign_type:
                  currentItem.campaign_type ||
                  campaignType,
                contact_name:
                  currentItem.contact_name ||
                  '',
                contact_title:
                  currentItem.contact_title ||
                  '',
              }),
            }
          );

        const data =
          await response.json();

        if (!response.ok) {
          setSendNote({
            msg:
              data.detail ||
              'Could not regenerate draft.',
            type: 'error',
          });
          return;
        }

        const itemType =
          currentItem.campaign_type ===
          'dogfood'
            ? 'dogfood'
            : 'normal';

        setSubject(
          data.draft_subject ||
          ''
        );

        setBody(
          finalizeSignature(
            data.draft_body ||
              '',
            displayName,
            itemType
          )
        );
      } catch (regenerateError: any) {
        setSendNote({
          msg:
            regenerateError.message ||
            'Could not regenerate draft.',
          type: 'error',
        });
      }
    };


  const sendOutreach =
    async () => {
      const currentItem =
        resultsQueue[
          currentIndex
        ];

      if (!currentItem) {
        return;
      }

      if (
        !gmailAddress ||
        !gmailAppPassword
      ) {
        setSendNote({
          msg:
            'Please provide both your Gmail address and Gmail App Password above.',
          type: 'error',
        });
        return;
      }

      if (
        !recipientEmail ||
        !/^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(
          recipientEmail
        )
      ) {
        setSendNote({
          msg:
            'Enter a valid recipient email address before sending.',
          type: 'error',
        });
        return;
      }

      setSendLoading(true);
      setSendNote(null);

      try {
        const demo =
          currentItem.demo_result ||
          {};

        const payload = {
          gmail_address:
            gmailAddress,
          gmail_app_password:
            gmailAppPassword,
          niche:
            campaignType ===
            'dogfood'
              ? DOGFOOD_NICHE
              : niche,
          location,
          scale,
          campaign_type:
            currentItem.campaign_type ||
            campaignType,
          recipient_email:
            recipientEmail,
          subject,
          body,
          business_name:
            currentItem.business_name,
          form_screenshot:
            demo.form_screenshot ||
            '',
          airtable_screenshot:
            demo.airtable_screenshot ||
            '',
          email_screenshot:
            demo.email_screenshot ||
            '',
          slack_screenshot:
            demo.slack_screenshot ||
            '',
        };

        const response =
          await fetch(
            `${API_BASE}/api/send-outreach`,
            {
              method: 'POST',
              headers: {
                'Content-Type':
                  'application/json',
                ...authHeaders,
              },
              body:
                JSON.stringify(
                  payload
                ),
            }
          );

        const data =
          await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail ||
            'Send failed.'
          );
        }

        setSendNote({
          msg:
            `Email sent via SMTP (${gmailAddress}) with inline proof images. Logged to History.`,
          type: 'success',
        });

        await fetchHistory();

        window.setTimeout(
          () => {
            if (
              currentIndex + 1 <
              resultsQueue.length
            ) {
              const nextIndex =
                currentIndex + 1;

              setCurrentIndex(
                nextIndex
              );

              loadQueueItem(
                resultsQueue[
                  nextIndex
                ]
              );
            }
          },
          1200
        );
      } catch (sendError: any) {
        setSendNote({
          msg:
            sendError.message ||
            'Send failed.',
          type: 'error',
        });
      } finally {
        setSendLoading(false);
      }
    };


  const currentItem =
    resultsQueue[
      currentIndex
    ];

  const totalPitched =
    historyItems.length;

  const estimatedHoursSaved =
    (
      totalPitched *
      0.75
    ).toFixed(1);

  const successRate =
    totalPitched > 0
      ? '100%'
      : '0%';


  const currentProofItems =
    currentItem &&
    currentItem.campaign_type ===
      'dogfood'
      ? [
          {
            key: 'form_screenshot',
            cap: '1. Scout dashboard',
          },
          {
            key: 'airtable_screenshot',
            cap: '2. Research breakdown',
          },
          {
            key: 'email_screenshot',
            cap: '3. Outreach draft',
          },
          {
            key: 'slack_screenshot',
            cap: '4. Sent-email proof',
          },
          {
            key: 'video_thumbnail',
            cap: '5. 3-minute walkthrough',
          },
        ]
      : [
          {
            key: 'form_screenshot',
            cap: '1. Intake form',
          },
          {
            key: 'airtable_screenshot',
            cap: '2. CRM record',
          },
          {
            key: 'email_screenshot',
            cap: '3. Auto-reply',
          },
          {
            key: 'slack_screenshot',
            cap: '4. Slack alert',
          },
        ];


  const historyProofItems = (
    item: any
  ) =>
    item?.campaign_type ===
    'dogfood'
      ? [
          {
            key: 'form_screenshot',
            cap: '1. Scout dashboard',
          },
          {
            key: 'airtable_screenshot',
            cap: '2. Research breakdown',
          },
          {
            key: 'email_screenshot',
            cap: '3. Outreach draft',
          },
          {
            key: 'slack_screenshot',
            cap: '4. Sent-email proof',
          },
        ]
      : [
          {
            key: 'form_screenshot',
            cap: '1. Intake form',
          },
          {
            key: 'airtable_screenshot',
            cap: '2. CRM record',
          },
          {
            key: 'email_screenshot',
            cap: '3. Auto-reply',
          },
          {
            key: 'slack_screenshot',
            cap: '4. Slack alert',
          },
        ];


  return (
    <div className="flex h-screen overflow-hidden bg-ink-950 font-sans text-white">

      {lightbox && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-ink-950/95 p-4 backdrop-blur-sm">
          <button
            onClick={() =>
              setLightbox(null)
            }
            className="absolute right-6 top-6 rounded-full p-2 hover:bg-white/10"
          >
            <X className="h-8 w-8 text-white" />
          </button>

          <img
            src={lightbox.url}
            alt={lightbox.cap}
            className="max-h-[82vh] max-w-[95vw] rounded-xl border border-white/10 object-contain shadow-2xl"
          />

          <div className="mt-4 text-center">
            <div className="font-medium text-white">
              {lightbox.cap}
            </div>
          </div>
        </div>
      )}


      <aside
        className={`${
          sidebarOpen
            ? 'w-64'
            : 'w-20'
        } flex shrink-0 flex-col border-r border-white/5 bg-ink-900/40 transition-all duration-300`}
      >
        <div className="flex items-center justify-between p-6">
          {sidebarOpen && (
            <span className="font-display text-xl font-bold">
              Scout<span className="text-scout-400">.</span>
            </span>
          )}

          <button
            onClick={() =>
              setSidebarOpen(
                (open) => !open
              )
            }
            className="rounded-lg p-1.5 text-ink-400 hover:bg-white/5 hover:text-white"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex flex-col gap-2 px-4">
          {[
            {
              value: 'home' as const,
              label: 'Home',
              icon: Home,
            },
            {
              value: 'history' as const,
              label: 'History',
              icon: History,
            },
            {
              value: 'analytics' as const,
              label: 'Analytics',
              icon: BarChart3,
            },
          ].map(
            (item) => {
              const Icon =
                item.icon;

              return (
                <button
                  key={item.value}
                  onClick={() => {
                    setActiveTab(
                      item.value
                    );
                    setSelectedHistoryItem(
                      null
                    );
                  }}
                  className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                    activeTab ===
                    item.value
                      ? 'bg-white/10 text-white'
                      : 'text-ink-400 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  {sidebarOpen &&
                    item.label}
                </button>
              );
            }
          )}
        </nav>

        <div className="mt-auto border-t border-white/5 p-6">
          {sidebarOpen ? (
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm text-ink-400">
                Hi, {displayName}
              </span>

              <button
                onClick={() =>
                  signOut()
                }
                title="Log out"
                className="shrink-0 rounded-lg p-1.5 text-ink-500 hover:bg-white/5 hover:text-white"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={() =>
                signOut()
              }
              title="Log out"
              className="text-sm text-ink-400 hover:text-white"
            >
              {displayName
                .charAt(0)
                .toUpperCase()}
            </button>
          )}
        </div>
      </aside>


      <main className="flex-1 overflow-y-auto p-10">
        <div className="mx-auto max-w-5xl">

          {activeTab === 'home' && (
            <div className="animate-fade-up">

              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h1 className="font-display text-3xl font-bold">
                    Home
                  </h1>

                  <p className="mt-2 text-ink-300">
                    {campaignType ===
                    'dogfood'
                      ? 'Find automation freelancers and agencies, pitch them Scout, and send the product proof inline.'
                      : "Point Scout at a niche, location, and run count — it'll take it from there."}
                  </p>
                </div>

                {founderAccess && (
                  <div className="min-w-[240px]">
                    <label className="mb-2 block text-xs font-medium text-ink-400">
                      Campaign
                    </label>

                    <select
                      value={
                        campaignType
                      }
                      onChange={(
                        event
                      ) =>
                        changeCampaign(
                          event
                            .target
                            .value as CampaignType
                        )
                      }
                      className="w-full rounded-xl border border-scout-400/20 bg-ink-900 px-4 py-2.5 text-sm text-white focus:border-scout-400 focus:outline-none"
                    >
                      <option value="normal">
                        Normal outreach
                      </option>

                      <option value="dogfood">
                        Dogfood • Promote Scout
                      </option>
                    </select>
                  </div>
                )}
              </div>


              {campaignType ===
                'dogfood' && (
                <div className="mt-6 rounded-2xl border border-scout-400/20 bg-scout-400/5 p-5">
                  <div className="text-xs font-semibold uppercase tracking-wider text-scout-400">
                    Founder campaign
                  </div>

                  <p className="mt-2 text-sm leading-relaxed text-ink-200">
                    Scout will target automation freelancers and agencies. The normal live demo builder is skipped, and the fixed Scout product screenshots are used instead.
                  </p>
                </div>
              )}


              <div className="glass-strong mt-8 grid gap-4 rounded-2xl p-6 sm:grid-cols-5 sm:items-end">

                <div className="flex flex-col gap-2 sm:col-span-1">
                  <label className="text-xs font-medium text-ink-400">
                    Niche
                  </label>

                  <input
                    value={
                      campaignType ===
                      'dogfood'
                        ? DOGFOOD_NICHE
                        : niche
                    }
                    onChange={(
                      event
                    ) =>
                      campaignType ===
                      'normal' &&
                      setNiche(
                        event.target.value
                      )
                    }
                    disabled={
                      campaignType ===
                      'dogfood'
                    }
                    placeholder="e.g. flower shops"
                    className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-scout-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-70"
                  />
                </div>


                <div className="flex flex-col gap-2">
                  <label className="text-xs font-medium text-ink-400">
                    Location
                  </label>

                  <input
                    value={
                      location
                    }
                    onChange={(
                      event
                    ) =>
                      setLocation(
                        event.target.value
                      )
                    }
                    placeholder="e.g. Colombo"
                    className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-scout-400 focus:outline-none"
                  />
                </div>


                <div className="flex flex-col gap-2">
                  <label className="text-xs font-medium text-ink-400">
                    Scale
                  </label>

                  <ScaleSelect
                    value={scale}
                    onChange={setScale}
                  />
                </div>


                <div className="flex flex-col gap-2">
                  <label className="text-xs font-medium text-ink-400">
                    Runs count
                  </label>

                  <CountSelect
                    value={count}
                    onChange={setCount}
                  />
                </div>


                <button
                  onClick={
                    runScout
                  }
                  disabled={
                    loading
                  }
                  className="flex h-[42px] items-center justify-center rounded-xl bg-gradient-to-r from-scout-400 to-aqua-500 font-semibold text-ink-950 transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-50"
                >
                  {loading
                    ? 'Running…'
                    : campaignType ===
                      'dogfood'
                      ? 'Run Dogfood'
                      : 'Run Scout'}
                </button>
              </div>


              {loading && (
                <div className="mt-6 flex items-center gap-3 text-scout-400">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  <span className="text-sm font-medium">
                    {status}
                  </span>
                </div>
              )}


              {error && (
                <div className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
                  {error}
                </div>
              )}


              {resultsQueue.length >
                0 &&
                !loading &&
                currentItem && (
                  <div className="mt-10 space-y-6">

                    {resultsQueue.length >
                      1 && (
                      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-scout-400/20 bg-scout-400/10 px-4 py-3 text-sm text-scout-300">
                        <span>
                          Queue progress: lead{' '}
                          <strong>
                            {currentIndex +
                              1}
                          </strong>{' '}
                          of{' '}
                          <strong>
                            {
                              resultsQueue.length
                            }
                          </strong>
                        </span>

                        <div className="flex gap-2">
                          {resultsQueue.map(
                            (_, index) => (
                              <button
                                key={index}
                                onClick={() => {
                                  setCurrentIndex(
                                    index
                                  );
                                  loadQueueItem(
                                    resultsQueue[
                                      index
                                    ]
                                  );
                                }}
                                className={`h-7 w-7 rounded-full text-xs font-bold ${
                                  currentIndex ===
                                  index
                                    ? 'bg-scout-400 text-ink-950'
                                    : 'bg-white/10 text-ink-300 hover:bg-white/20'
                                }`}
                              >
                                {index + 1}
                              </button>
                            )
                          )}
                        </div>
                      </div>
                    )}


                    <div className="glass rounded-2xl p-6">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                            Target business
                          </div>

                          <h2 className="mt-2 font-display text-2xl font-bold">
                            {
                              currentItem.business_name
                            }
                          </h2>
                        </div>

                        <span className="rounded-full bg-white/5 px-3 py-1 text-xs font-medium text-ink-300">
                          {currentItem.campaign_type ===
                          'dogfood'
                            ? 'Dogfood'
                            : 'Normal outreach'}
                        </span>
                      </div>


                      <div className="mt-5 grid gap-3 sm:grid-cols-2">

                        <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                            Official website
                          </div>

                          {currentItem.website ? (
                            <a
                              href={
                                currentItem.website
                              }
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 block truncate text-sm text-scout-400 hover:underline"
                            >
                              {
                                currentItem.website
                              }
                            </a>
                          ) : (
                            <div className="mt-1 text-sm text-ink-400">
                              Not found
                            </div>
                          )}
                        </div>

                        <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                            Domain
                          </div>

                          <div className="mt-1 text-sm text-ink-200">
                            {currentItem.domain ||
                              'Not found'}
                          </div>
                        </div>

                        <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                            Website email found by Linkup
                          </div>

                          <div className="mt-1 flex items-center gap-2 break-all text-sm text-ink-200">
                            <Mail className="h-3.5 w-3.5 shrink-0 text-ink-500" />
                            {currentItem.website_email ||
                              'Not found'}
                          </div>
                        </div>

                        <div className="rounded-xl border border-white/5 bg-white/5 p-4">
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-500">
                            Automation opportunity
                          </div>

                          <div className="mt-1 text-sm leading-relaxed text-ink-200">
                            {
                              currentItem.automation_opportunity ||
                              'Not found'
                            }
                          </div>
                        </div>
                      </div>


                      <div className="mt-4 rounded-xl border border-scout-400/15 bg-scout-400/5 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-[10px] font-semibold uppercase tracking-wider text-scout-400">
                            Contact enrichment
                          </div>

                          <div className="text-[10px] uppercase tracking-wider text-ink-500">
                            {currentItem.contact_source ||
                              'Linkup fallback'}
                          </div>
                        </div>

                        {currentItem.contact_email ? (
                          <div className="mt-3 grid gap-3 sm:grid-cols-3">
                            <div>
                              <div className="text-[10px] uppercase tracking-wider text-ink-500">
                                Person
                              </div>

                              <div className="mt-1 text-sm font-medium text-white">
                                {
                                  currentItem.contact_name ||
                                  'Name unavailable'
                                }
                              </div>
                            </div>

                            <div>
                              <div className="text-[10px] uppercase tracking-wider text-ink-500">
                                Position
                              </div>

                              <div className="mt-1 text-sm text-ink-200">
                                {
                                  currentItem.contact_title ||
                                  'Position unavailable'
                                }
                              </div>
                            </div>

                            <div>
                              <div className="text-[10px] uppercase tracking-wider text-ink-500">
                                Personal email
                              </div>

                              <div className="mt-1 break-all text-sm text-scout-400">
                                {
                                  currentItem.contact_email
                                }
                              </div>

                              <div className="mt-1 text-[10px] text-ink-500">
                                {currentItem.contact_seniority ||
                                  ''}
                                {currentItem.contact_confidence
                                  ? ` • ${currentItem.contact_confidence}% confidence`
                                  : ''}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-2 text-sm text-ink-300">
                            Hunter did not find a suitable personal decision-maker.
                            Scout will use the exact website email found by Linkup as
                            the recipient.
                          </div>
                        )}
                      </div>


                      <div className="mt-5 max-h-64 overflow-y-auto whitespace-pre-wrap border-t border-white/5 pt-4 text-sm leading-relaxed text-ink-300">
                        {
                          currentItem.research_profile
                        }
                      </div>
                    </div>


                    <div className="glass rounded-2xl p-6">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                            {currentItem.campaign_type ===
                            'dogfood'
                              ? 'Scout product proof'
                              : 'Proof of the demo'}
                          </h2>

                          {currentItem.campaign_type ===
                            'dogfood' && (
                            <p className="mt-1 text-xs text-ink-500">
                              These exact product images are what Scout will place inline in the email.
                            </p>
                          )}
                        </div>
                      </div>

                      <div className={`mt-4 grid gap-4 ${
                        currentItem.campaign_type ===
                        'dogfood'
                          ? 'sm:grid-cols-5'
                          : 'sm:grid-cols-4'
                      }`}>
                        {currentProofItems.map(
                          (proof) => {
                            const url =
                              getImageUrl(
                                currentItem
                                  .demo_result?.[
                                  proof.key
                                ]
                              );

                            if (!url) {
                              return null;
                            }

                            return (
                              <div
                                key={
                                  proof.key
                                }
                                onClick={() =>
                                  setLightbox({
                                    url,
                                    cap: proof.cap,
                                  })
                                }
                                className="group cursor-pointer overflow-hidden rounded-xl border border-white/10 bg-ink-900/50 hover:border-scout-400"
                              >
                                <img
                                  src={url}
                                  alt={
                                    proof.cap
                                  }
                                  className="h-28 w-full object-cover object-top opacity-80 transition-opacity group-hover:opacity-100"
                                />

                                <div className="flex items-center gap-2 p-2.5 text-xs text-ink-300">
                                  <ImageIcon className="h-3.5 w-3.5 text-scout-400" />
                                  {
                                    proof.cap
                                  }
                                </div>
                              </div>
                            );
                          }
                        )}
                      </div>
                    </div>


                    <div className="glass rounded-2xl border border-scout-400/20 p-6">
                      <div className="flex items-center justify-between">
                        <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-scout-400">
                          <Key className="h-4 w-4" />
                          Native Mailbox Settings (SMTP)
                        </h2>

                        <span
                          className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase ${
                            mailboxConnected
                              ? 'bg-emerald-400/10 text-emerald-300'
                              : 'bg-scout-400/10 text-scout-300'
                          }`}
                        >
                          {mailboxConnected
                            ? `Connected (${gmailAddress})`
                            : 'Not connected'}
                        </span>
                      </div>

                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <div className="flex flex-col gap-2">
                          <label className="text-xs font-medium text-ink-400">
                            Gmail Address
                          </label>

                          <div className="relative">
                            <input
                              type="email"
                              value={
                                gmailAddress
                              }
                              onChange={(
                                event
                              ) =>
                                handleGmailAddressChange(
                                  event
                                    .target
                                    .value
                                )
                              }
                              placeholder="your.email@gmail.com"
                              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white focus:border-scout-400 focus:outline-none"
                            />
                          </div>
                        </div>

                        <div className="flex flex-col gap-2">
                          <label className="text-xs font-medium text-ink-400">
                            Gmail App Password
                          </label>

                          <div className="relative">
                            <input
                              type={
                                showPassword
                                  ? 'text'
                                  : 'password'
                              }
                              value={
                                gmailAppPassword
                              }
                              onChange={(
                                event
                              ) =>
                                handleGmailPasswordChange(
                                  event
                                    .target
                                    .value
                                )
                              }
                              placeholder="xxxx xxxx xxxx xxxx"
                              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2 pr-10 text-sm font-mono text-white focus:border-scout-400 focus:outline-none"
                            />

                            <button
                              type="button"
                              onClick={() =>
                                setShowPassword(
                                  (
                                    visible
                                  ) =>
                                    !visible
                                )
                              }
                              className="absolute right-3 top-2.5 text-ink-400 hover:text-white"
                            >
                              {showPassword ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                        </div>
                      </div>

                      <p className="mt-3 text-xs text-ink-500">
                        Generate an App Password via Google Account
                        &gt; Security &gt; 2-Step Verification.
                      </p>

                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          onClick={
                            saveMailboxSettings
                          }
                          disabled={
                            mailboxSaving
                          }
                          className="rounded-xl bg-scout-400 px-4 py-2 text-sm font-semibold text-ink-950 hover:bg-scout-300 disabled:opacity-50"
                        >
                          {mailboxSaving
                            ? 'Connecting…'
                            : mailboxConnected
                              ? 'Reconnect mailbox'
                              : 'Connect mailbox'}
                        </button>

                        {mailboxNote && (
                          <span
                            className={`text-xs ${
                              mailboxNote.type ===
                              'success'
                                ? 'text-emerald-300'
                                : 'text-red-300'
                            }`}
                          >
                            {
                              mailboxNote.msg
                            }
                          </span>
                        )}
                      </div>
                    </div>


                    <div className="glass-strong rounded-2xl p-6">
                      <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-ink-400">
                        Outreach — review before sending
                      </h2>

                      <div className="space-y-4">
                        <div className="flex flex-col gap-2">
                          <label className="text-xs font-medium text-ink-400">
                            Send to
                          </label>

                          <input
                            value={
                              recipientEmail
                            }
                            onChange={(
                              event
                            ) =>
                              setRecipientEmail(
                                event
                                  .target
                                  .value
                              )
                            }
                            placeholder="contact@business.com"
                            className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white focus:border-scout-400 focus:outline-none"
                          />

                          <p className="text-xs text-ink-500">
                            {currentItem.contact_email
                              ? 'Personal contact found by Hunter. The Linkup website email remains the fallback.'
                              : currentItem.website_email
                                ? 'No suitable personal contact was found by Hunter, so Scout is using the exact website email found by Linkup.'
                                : 'Scout could not find a recipient automatically. Enter one manually before sending.'}
                          </p>
                        </div>

                        <div className="flex flex-col gap-2">
                          <label className="text-xs font-medium text-ink-400">
                            Subject
                          </label>

                          <input
                            value={
                              subject
                            }
                            onChange={(
                              event
                            ) =>
                              setSubject(
                                event
                                  .target
                                  .value
                              )
                            }
                            className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-white focus:border-scout-400 focus:outline-none"
                          />
                        </div>

                        <div className="flex flex-col gap-2">
                          <label className="text-xs font-medium text-ink-400">
                            Message
                          </label>

                          <textarea
                            value={
                              body
                            }
                            onChange={(
                              event
                            ) =>
                              setBody(
                                event
                                  .target
                                  .value
                              )
                            }
                            rows={
                              currentItem.campaign_type ===
                              'dogfood'
                                ? 13
                                : 8
                            }
                            className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-ink-200 focus:border-scout-400 focus:outline-none"
                          />
                        </div>

                        <div className="flex flex-wrap items-center gap-3 pt-2">
                          <button
                            onClick={
                              regenerateOutreach
                            }
                            className="rounded-xl border border-white/10 bg-transparent px-5 py-2.5 text-sm font-medium hover:border-white/30 hover:bg-white/5"
                          >
                            Regenerate draft
                          </button>

                          <button
                            onClick={
                              sendOutreach
                            }
                            disabled={
                              sendLoading
                            }
                            className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-scout-400 to-aqua-500 px-6 py-2.5 text-sm font-semibold text-ink-950 transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-50"
                          >
                            {sendLoading && (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            )}
                            Approve & send
                          </button>

                          {sendNote && (
                            <span
                              className={`text-sm font-medium ${
                                sendNote.type ===
                                'success'
                                  ? 'text-scout-400'
                                  : 'text-red-400'
                              }`}
                            >
                              {
                                sendNote.msg
                              }
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
            </div>
          )}


          {activeTab === 'history' && (
            <div className="animate-fade-up">
              {selectedHistoryItem ? (
                <div className="space-y-6">
                  <button
                    onClick={() =>
                      setSelectedHistoryItem(
                        null
                      )
                    }
                    className="flex items-center gap-2 text-sm text-ink-400 hover:text-white"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Back to History list
                  </button>

                  <div className="glass rounded-2xl p-6">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="font-display text-2xl font-bold">
                            {
                              selectedHistoryItem.business_name
                            }
                          </h2>

                          <span className="rounded-full bg-scout-400/10 px-3 py-1 text-xs font-semibold text-scout-400">
                            {selectedHistoryItem.campaign_type ===
                            'dogfood'
                              ? 'Dogfood'
                              : 'Normal'}
                          </span>
                        </div>

                        <p className="mt-3 text-sm text-ink-400">
                          Sent to{' '}
                          {
                            selectedHistoryItem.recipient_email
                          }
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-4 text-xs text-ink-400">
                      <span className="flex items-center gap-1">
                        <Globe className="h-3.5 w-3.5" />
                        Niche:{' '}
                        {
                          selectedHistoryItem.niche
                        }
                      </span>

                      <span className="flex items-center gap-1">
                        <MapPin className="h-3.5 w-3.5" />
                        Location:{' '}
                        {
                          selectedHistoryItem.location
                        }
                      </span>

                      <span>
                        Scale:{' '}
                        {
                          selectedHistoryItem.scale
                        }
                      </span>
                    </div>
                  </div>

                  <div className="glass rounded-2xl p-6">
                    <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-ink-400">
                      Inline proof images
                    </h2>

                    <div className="grid gap-4 sm:grid-cols-4">
                      {historyProofItems(
                        selectedHistoryItem
                      ).map(
                        (proof) =>
                          selectedHistoryItem[
                            proof.key
                          ] && (
                            <div
                              key={
                                proof.key
                              }
                              onClick={() =>
                                setLightbox({
                                  url: getImageUrl(
                                    selectedHistoryItem[
                                      proof.key
                                    ]
                                  ),
                                  cap: proof.cap,
                                })
                              }
                              className="group cursor-pointer overflow-hidden rounded-xl border border-white/10 bg-ink-900/50 hover:border-scout-400"
                            >
                              <img
                                src={getImageUrl(
                                  selectedHistoryItem[
                                    proof.key
                                  ]
                                )}
                                alt={
                                  proof.cap
                                }
                                className="h-28 w-full object-cover object-top opacity-80 group-hover:opacity-100"
                              />

                              <div className="flex items-center gap-2 p-2.5 text-xs text-ink-300">
                                <ImageIcon className="h-3.5 w-3.5 text-scout-400" />
                                {
                                  proof.cap
                                }
                              </div>
                            </div>
                          )
                      )}
                    </div>
                  </div>

                  <div className="glass-strong space-y-4 rounded-2xl p-6">
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                      Outreach Email Sent
                    </h2>

                    <div>
                      <div className="text-xs text-ink-400">
                        Subject
                      </div>

                      <div className="mt-1 text-sm font-medium text-white">
                        {
                          selectedHistoryItem.subject
                        }
                      </div>
                    </div>

                    <div>
                      <div className="text-xs text-ink-400">
                        Body
                      </div>

                      <div className="mt-1 whitespace-pre-wrap rounded-xl border border-white/5 bg-white/5 p-4 text-sm text-ink-300">
                        {
                          selectedHistoryItem.body
                        }
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div>
                  <h1 className="font-display text-3xl font-bold">
                    History
                  </h1>

                  <p className="mt-2 text-ink-300">
                    Every business you've
                    reached out to appears
                    here.
                  </p>

                  {historyItems.length ===
                  0 ? (
                    <div className="mt-8 rounded-2xl border border-dashed border-white/10 p-12 text-center text-sm text-ink-400">
                      No outreach sent yet.
                      Once you approve and
                      send from Home, it will
                      appear here.
                    </div>
                  ) : (
                    <div className="mt-8 grid gap-4">
                      {historyItems.map(
                        (item) => (
                          <div
                            key={item.id}
                            onClick={() =>
                              setSelectedHistoryItem(
                                item
                              )
                            }
                            className="glass group flex cursor-pointer items-center justify-between rounded-2xl p-5 transition-all hover:border-scout-400"
                          >
                            <div>
                              <div className="flex items-center gap-2">
                                <h3 className="font-display text-lg font-bold group-hover:text-scout-400">
                                  {
                                    item.business_name
                                  }
                                </h3>

                                <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-ink-400">
                                  {item.campaign_type ===
                                  'dogfood'
                                    ? 'Dogfood'
                                    : 'Normal'}
                                </span>
                              </div>

                              <p className="mt-1 text-xs text-ink-400">
                                {item.niche}
                                {' • '}
                                {
                                  item.location
                                }
                                {' • Sent to '}
                                {
                                  item.recipient_email
                                }
                              </p>
                            </div>

                            <div className="text-right text-xs text-ink-400">
                              {new Date(
                                item.created_at
                              ).toLocaleDateString()}
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}


          {activeTab === 'analytics' && (
            <div className="animate-fade-up">
              <h1 className="font-display text-3xl font-bold">
                Analytics & Impact
              </h1>

              <p className="mt-2 text-ink-300">
                Performance metrics for your
                outreach engine.
              </p>

              <div className="mt-8 grid gap-6 sm:grid-cols-3">
                <div className="glass rounded-2xl p-6">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                      Total Pitched
                    </span>
                    <Target className="h-5 w-5 text-scout-400" />
                  </div>

                  <div className="mt-4 font-display text-4xl font-bold">
                    {totalPitched}
                  </div>

                  <p className="mt-2 text-xs text-ink-400">
                    Businesses successfully
                    researched and emailed.
                  </p>
                </div>

                <div className="glass rounded-2xl p-6">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                      Est. Hours Saved
                    </span>
                    <Clock className="h-5 w-5 text-aqua-400" />
                  </div>

                  <div className="mt-4 font-display text-4xl font-bold">
                    {estimatedHoursSaved}{' '}
                    hrs
                  </div>

                  <p className="mt-2 text-xs text-ink-400">
                    Estimated from your
                    outreach activity.
                  </p>
                </div>

                <div className="glass rounded-2xl p-6">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                      Execution Success
                    </span>
                    <Zap className="h-5 w-5 text-amber-400" />
                  </div>

                  <div className="mt-4 font-display text-4xl font-bold">
                    {successRate}
                  </div>

                  <p className="mt-2 text-xs text-ink-400">
                    Successful sends recorded
                    by this workspace.
                  </p>
                </div>
              </div>

              <div className="glass-strong mt-8 rounded-2xl p-6">
                <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-ink-400">
                  Activity Breakdown
                </h2>

                {historyItems.length ===
                0 ? (
                  <p className="py-6 text-center text-sm text-ink-400">
                    No activity recorded yet.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {historyItems.map(
                      (
                        item,
                        index
                      ) => (
                        <div
                          key={
                            item.id ||
                            index
                          }
                          className="flex items-center justify-between rounded-xl bg-white/5 p-4 text-sm"
                        >
                          <div>
                            <span className="font-semibold text-white">
                              {
                                item.business_name
                              }
                            </span>

                            <span className="ml-3 text-xs text-ink-400">
                              {
                                item.niche
                              }{' '}
                              (
                              {
                                item.location
                              }
                              )
                            </span>
                          </div>

                          <span className="rounded-full bg-scout-400/10 px-3 py-1 text-xs font-medium text-scout-400">
                            {new Date(
                              item.created_at
                            ).toLocaleDateString()}
                          </span>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
