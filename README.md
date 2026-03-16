## SafeVoice-AI - System Architecture

<svg width="1360" height="1480" viewBox="0 0 680 740" xmlns="http://www.w3.org/2000/svg" font-family="Arial, sans-serif">
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="#888780" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
</defs>

<!-- background -->
<rect width="680" height="740" fill="#ffffff"/>

<!-- Title -->
<text x="340" y="16" text-anchor="middle" font-size="13" font-weight="500" fill="#2C2C2A">SafeVoice AI — System Architecture</text>

<!-- ── MOBILE LAYER ── -->
<rect x="30" y="24" width="180" height="200" rx="12" fill="#F1EFE8" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="120" y="46" text-anchor="middle" font-size="14" font-weight="500" fill="#444441" dominant-baseline="central">Mobile app</text>
<text x="120" y="62" text-anchor="middle" font-size="12" fill="#5F5E5A" dominant-baseline="central">React Native</text>

<rect x="50" y="78" width="140" height="38" rx="6" fill="#D3D1C7" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="120" y="93" text-anchor="middle" font-size="14" font-weight="500" fill="#444441" dominant-baseline="central">Keyword spotter</text>
<text x="120" y="109" text-anchor="middle" font-size="12" fill="#5F5E5A" dominant-baseline="central">On-device, private</text>

<rect x="50" y="126" width="140" height="38" rx="6" fill="#D3D1C7" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="120" y="141" text-anchor="middle" font-size="14" font-weight="500" fill="#444441" dominant-baseline="central">Audio streamer</text>
<text x="120" y="157" text-anchor="middle" font-size="12" fill="#5F5E5A" dominant-baseline="central">PCM 16kHz</text>

<rect x="50" y="174" width="140" height="38" rx="6" fill="#D3D1C7" stroke="#5F5E5A" stroke-width="0.5"/>
<text x="120" y="189" text-anchor="middle" font-size="14" font-weight="500" fill="#444441" dominant-baseline="central">Silent trigger</text>
<text x="120" y="205" text-anchor="middle" font-size="12" fill="#5F5E5A" dominant-baseline="central">Shake + power btn</text>

<!-- WSS label -->
<line x1="210" y1="152" x2="248" y2="152" stroke="#378ADD" stroke-width="1" marker-end="url(#arrow)"/>
<text x="229" y="145" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">WSS</text>

<!-- ── GEMINI LIVE API ── -->
<rect x="248" y="24" width="180" height="200" rx="12" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="338" y="46" text-anchor="middle" font-size="14" font-weight="500" fill="#085041" dominant-baseline="central">Gemini Live API</text>
<text x="338" y="62" text-anchor="middle" font-size="12" fill="#0F6E56" dominant-baseline="central">gemini-2.0-flash-live</text>

<rect x="268" y="78" width="140" height="38" rx="6" fill="#9FE1CB" stroke="#0F6E56" stroke-width="0.5"/>
<text x="338" y="93" text-anchor="middle" font-size="14" font-weight="500" fill="#085041" dominant-baseline="central">Voice detection</text>
<text x="338" y="109" text-anchor="middle" font-size="12" fill="#0F6E56" dominant-baseline="central">Start/end sensitivity</text>

<rect x="268" y="126" width="140" height="38" rx="6" fill="#9FE1CB" stroke="#0F6E56" stroke-width="0.5"/>
<text x="338" y="141" text-anchor="middle" font-size="14" font-weight="500" fill="#085041" dominant-baseline="central">Stress analysis</text>
<text x="338" y="157" text-anchor="middle" font-size="12" fill="#0F6E56" dominant-baseline="central">Pitch, energy, rate</text>

<rect x="268" y="174" width="140" height="38" rx="6" fill="#9FE1CB" stroke="#0F6E56" stroke-width="0.5"/>
<text x="338" y="189" text-anchor="middle" font-size="14" font-weight="500" fill="#085041" dominant-baseline="central">Barge-in window</text>
<text x="338" y="205" text-anchor="middle" font-size="12" fill="#0F6E56" dominant-baseline="central">3s cancel, then fire</text>

<!-- Confirmed arrow -->
<line x1="428" y1="152" x2="466" y2="152" stroke="#1D9E75" stroke-width="1" marker-end="url(#arrow)"/>
<text x="447" y="145" text-anchor="middle" font-size="12" fill="#0F6E56" dominant-baseline="central">Confirmed</text>

<!-- ── ADK AGENT ── -->
<rect x="466" y="24" width="184" height="200" rx="12" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text x="558" y="46" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489" dominant-baseline="central">ADK agent</text>
<text x="558" y="62" text-anchor="middle" font-size="12" fill="#534AB7" dominant-baseline="central">Cloud Run</text>

<rect x="486" y="78" width="144" height="38" rx="6" fill="#CECBF6" stroke="#534AB7" stroke-width="0.5"/>
<text x="558" y="93" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489" dominant-baseline="central">State machine</text>
<text x="558" y="109" text-anchor="middle" font-size="12" fill="#534AB7" dominant-baseline="central">IDLE→ACTIVE→RESOLVED</text>

<rect x="486" y="126" width="144" height="38" rx="6" fill="#CECBF6" stroke="#534AB7" stroke-width="0.5"/>
<text x="558" y="141" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489" dominant-baseline="central">Parallel tools</text>
<text x="558" y="157" text-anchor="middle" font-size="12" fill="#534AB7" dominant-baseline="central">asyncio.gather()</text>

<rect x="486" y="174" width="144" height="38" rx="6" fill="#CECBF6" stroke="#534AB7" stroke-width="0.5"/>
<text x="558" y="189" text-anchor="middle" font-size="14" font-weight="500" fill="#3C3489" dominant-baseline="central">Check-in loop</text>
<text x="558" y="205" text-anchor="middle" font-size="12" fill="#534AB7" dominant-baseline="central">30 min GPS + safe?</text>

<!-- Divider -->
<line x1="30" y1="252" x2="650" y2="252" stroke="#D3D1C7" stroke-width="0.5" stroke-dasharray="4 4"/>
<text x="340" y="264" text-anchor="middle" font-size="12" fill="#888780" dominant-baseline="central">Emergency response — all 5 tools fire in parallel (asyncio.gather)</text>

<!-- ── TOOL ROW ── -->
<rect x="30" y="282" width="108" height="54" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text x="84" y="303" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13" dominant-baseline="central">get_gps()</text>
<text x="84" y="321" text-anchor="middle" font-size="12" fill="#993C1D" dominant-baseline="central">Maps Platform</text>

<rect x="152" y="282" width="108" height="54" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text x="206" y="303" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13" dominant-baseline="central">send_sms()</text>
<text x="206" y="321" text-anchor="middle" font-size="12" fill="#993C1D" dominant-baseline="central">Twilio SMS</text>

<rect x="274" y="282" width="108" height="54" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text x="328" y="303" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13" dominant-baseline="central">call_helpline()</text>
<text x="328" y="321" text-anchor="middle" font-size="12" fill="#993C1D" dominant-baseline="central">Twilio Voice</text>

<rect x="396" y="282" width="118" height="54" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text x="455" y="303" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13" dominant-baseline="central">notify_contacts()</text>
<text x="455" y="321" text-anchor="middle" font-size="12" fill="#993C1D" dominant-baseline="central">WhatsApp + FCM</text>

<rect x="528" y="282" width="122" height="54" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text x="589" y="303" text-anchor="middle" font-size="14" font-weight="500" fill="#712B13" dominant-baseline="central">log_incident()</text>
<text x="589" y="321" text-anchor="middle" font-size="12" fill="#993C1D" dominant-baseline="central">Firestore write</text>

<!-- ADK → tools fan arrows -->
<path d="M510 224 L510 252 L84 252 L84 282" fill="none" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<path d="M530 224 L530 252 L206 252 L206 282" fill="none" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<path d="M558 224 L558 252 L328 252 L328 282" fill="none" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<path d="M586 224 L586 252 L455 252 L455 282" fill="none" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<path d="M606 224 L606 252 L589 252 L589 282" fill="none" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>

<!-- ── GCP INFRA LAYER ── -->
<rect x="30" y="372" width="620" height="160" rx="12" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="340" y="394" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Google Cloud infrastructure</text>

<rect x="50" y="408" width="120" height="50" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="110" y="426" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Cloud Run</text>
<text x="110" y="444" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">min 1 instance</text>

<rect x="186" y="408" width="110" height="50" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="241" y="426" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Vertex AI</text>
<text x="241" y="444" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">Voice biometrics</text>

<rect x="312" y="408" width="104" height="50" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="364" y="426" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Firestore</text>
<text x="364" y="444" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">Users + incidents</text>

<rect x="432" y="408" width="110" height="50" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="487" y="426" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Cloud Storage</text>
<text x="487" y="444" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">Voice recordings</text>

<rect x="558" y="408" width="82" height="50" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="599" y="426" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Secrets</text>
<text x="599" y="444" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">Secret Manager</text>

<rect x="50" y="470" width="240" height="42" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="170" y="487" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Cloud Build + Artifact Registry</text>
<text x="170" y="503" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">CI/CD — auto deploy on git push</text>

<rect x="306" y="470" width="140" height="42" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="376" y="487" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Maps Platform</text>
<text x="376" y="503" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">GPS + geocoding</text>

<rect x="462" y="470" width="178" height="42" rx="6" fill="#B5D4F4" stroke="#185FA5" stroke-width="0.5"/>
<text x="551" y="487" text-anchor="middle" font-size="14" font-weight="500" fill="#0C447C" dominant-baseline="central">Firebase FCM</text>
<text x="551" y="503" text-anchor="middle" font-size="12" fill="#185FA5" dominant-baseline="central">Push notifications + SMS</text>

<!-- Tools → GCP -->
<line x1="84" y1="336" x2="84" y2="372" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="206" y1="336" x2="206" y2="372" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="328" y1="336" x2="328" y2="372" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="455" y1="336" x2="455" y2="372" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="589" y1="336" x2="589" y2="372" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>

<!-- ── EXTERNAL SERVICES ── -->
<text x="340" y="556" text-anchor="middle" font-size="12" fill="#888780" dominant-baseline="central">External services</text>

<rect x="30" y="570" width="140" height="50" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="100" y="588" text-anchor="middle" font-size="14" font-weight="500" fill="#633806" dominant-baseline="central">Twilio</text>
<text x="100" y="606" text-anchor="middle" font-size="12" fill="#854F0B" dominant-baseline="central">SMS + Voice calls</text>

<rect x="186" y="570" width="150" height="50" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="261" y="588" text-anchor="middle" font-size="14" font-weight="500" fill="#633806" dominant-baseline="central">WhatsApp API</text>
<text x="261" y="606" text-anchor="middle" font-size="12" fill="#854F0B" dominant-baseline="central">Contact alerts</text>

<rect x="352" y="570" width="150" height="50" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="427" y="588" text-anchor="middle" font-size="14" font-weight="500" fill="#633806" dominant-baseline="central">Helplines</text>
<text x="427" y="606" text-anchor="middle" font-size="12" fill="#854F0B" dominant-baseline="central">181 women / 112 police</text>

<rect x="518" y="570" width="132" height="50" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="584" y="588" text-anchor="middle" font-size="14" font-weight="500" fill="#633806" dominant-baseline="central">Emergency contacts</text>
<text x="584" y="606" text-anchor="middle" font-size="12" fill="#854F0B" dominant-baseline="central">Family + friends</text>

<!-- GCP → external -->
<line x1="100" y1="532" x2="100" y2="570" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="261" y1="532" x2="261" y2="570" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="427" y1="532" x2="427" y2="570" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>
<line x1="584" y1="532" x2="584" y2="570" stroke="#B4B2A9" stroke-width="0.5" marker-end="url(#arrow)"/>

<!-- ── LEGEND ── -->
<rect x="30" y="648" width="14" height="14" rx="3" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text x="50" y="656" font-size="12" fill="#5F5E5A" dominant-baseline="central">Emergency tools</text>
<rect x="160" y="648" width="14" height="14" rx="3" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text x="180" y="656" font-size="12" fill="#5F5E5A" dominant-baseline="central">ADK agent</text>
<rect x="270" y="648" width="14" height="14" rx="3" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text x="290" y="656" font-size="12" fill="#5F5E5A" dominant-baseline="central">Gemini Live API</text>
<rect x="400" y="648" width="14" height="14" rx="3" fill="#E6F1FB" stroke="#185FA5" stroke-width="0.5"/>
<text x="420" y="656" font-size="12" fill="#5F5E5A" dominant-baseline="central">Google Cloud</text>
<rect x="520" y="648" width="14" height="14" rx="3" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text x="540" y="656" font-size="12" fill="#5F5E5A" dominant-baseline="central">External</text>

<text x="340" y="706" text-anchor="middle" font-size="11" fill="#888780" dominant-baseline="central">SafeVoice AI — #GeminiLiveAgentChallenge — Gemini Live API + ADK + Google Cloud</text>
</svg>
file is completed 
