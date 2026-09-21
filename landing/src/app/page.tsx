import BackgroundLayers from "@/components/BackgroundLayers";
import NoiseOverlay from "@/components/NoiseOverlay";
import ScrollProgress from "@/components/ScrollProgress";
import {
  Closing,
  Faq,
} from "@/components/home/ConversionSections";
import { Footer, Header } from "@/components/home/HomeChrome";
import {
  Caliber,
  Insights,
  Roles,
} from "@/components/home/InsightSections";
import {
  Capabilities,
  Hero,
  Method,
  PlatformStrip,
} from "@/components/home/OverviewSections";

export default function Page() {
  return (
    <div className="relative min-h-[100dvh] overflow-x-hidden bg-page font-sans text-txt antialiased">
      <BackgroundLayers />
      <ScrollProgress />
      <NoiseOverlay />
      <Header />
      <main className="relative z-10 w-full max-w-full">
        <Hero />
        <PlatformStrip />
        <Method />
        <Capabilities />
        <Insights />
        <Roles />
        <Caliber />
        <Faq />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}
