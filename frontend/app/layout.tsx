import './styles.css';
import './forms.css';
// Render per request so the middleware's per-request CSP nonce reaches the scripts
// Next generates. A statically prerendered page is rendered once at build time,
// when no nonce exists, so `script-src` could not drop 'unsafe-inline'.
export const dynamic = 'force-dynamic';
export const metadata={title:'FinRisk-Agent',description:'Evidence-grounded corporate risk assessment'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
