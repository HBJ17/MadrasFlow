// English / Tamil labels for the UI chrome and crowd levels.
import { createContext, useContext } from 'react'

export type Lang = 'en' | 'ta'

const dict = {
  en: {
    app: 'MadrasFlow', tagline: 'South Chennai crowd forecast', simulated: 'Simulated data',
    simulatedLong: 'Numbers come from a calibrated simulation, not live passenger counts.',
    search: 'Search a stop or route', planTrip: 'Plan a trip', favourites: 'Saved stops', routes: 'Routes', nearby: 'Nearby stops',
    findNearby: 'Find stops near me', noFav: 'Tap ☆ on a stop to save it here.', lastUpdated: 'Offline · last updated',
    now: 'Now', in30: 'In 30 min', in60: 'In 1 h', direction: 'Direction', nextVehicle: 'next', min: 'min',
    upcoming: 'Next departures', waitOrGo: 'Wait or go?', from: 'From', to: 'To', departNow: 'Leave now', departAt: 'Leave at',
    preferLow: 'Prefer less crowded', preferLowHint: 'For seniors, women travelling alone, people with luggage', go: 'Find routes',
    fastest: 'Fastest', least_crowded: 'Least crowded', balanced: 'Balanced', alternative: 'Alternative',
    transfers: 'transfers', transfer: 'transfer', walk: 'Walk', worst: 'Busiest', arrive: 'Arrive', back: 'Back',
    vehicle: 'Vehicle', load: 'Estimated load', nextStops: 'Next stops', showMap: 'Show map', hideMap: 'Hide map',
    depot: 'Depot dashboard', depotShort: 'Depot', commuter: 'Commuter', loading: 'Loading…', retry: 'Retry', noData: 'No forecast yet — the forecast job runs every 5 minutes.',
    stale: 'No live data in the last 10 min', board: 'Board', alight: 'Get off', stops: 'stops', save: 'Save stop', saved: 'Saved',
    LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High', CROWDED: 'Crowded', full: 'full',
    currentLocation: 'Current location', locating: 'Finding your location…', locationDenied: 'Location unavailable. Pick a stop instead.',
    near: 'near', minWalk: 'min walk', windowLabel: 'Window', widen: 'Widen the window by 15 minutes', narrow: 'Narrow the window by 15 minutes',
    rankBy: 'Rank by', rankCrowd: 'Crowd', rankEta: 'Arrival time', rankCost: 'Cost', rankWalk: 'Walking', rankTransfers: 'Transfers',
    filters: 'Filters', apply: 'Apply', reset: 'Reset', modes: 'Modes', bus: 'Bus', mrts: 'MRTS', metro: 'Metro',
    maxWalk: 'Longest walk', any: 'Any', maxFare: 'Highest fare', maxTransfers: 'Transfers', direct: 'Direct only', upTo1: 'Up to 1',
    accessibility: 'Accessibility', stepFree: 'Step-free stations', stepFreeHint: 'Stations with lifts; low-floor bus not guaranteed',
    women: "Women's travel", womenHint: 'Free on MTC ordinary buses; short walks and waits after dark',
    leave: 'Leave', options: 'options', noRoutesSlot: 'No route matches your filters at this time.', bestOverall: 'Best overall',
    free_bus_women: 'Bus free for women', low_floor: 'Low-floor bus not guaranteed', after_dark: 'After dark: short walks and waits',
    routeMap: 'Route on the map', mapOffline: 'Map unavailable offline. The steps below still work.', prevSlot: 'Earlier departure', nextSlot: 'Later departure',
    fare: 'Fare', updating: 'Updating…', pickStops: 'Pick both stops from the list', useStop: 'Choose a stop', useLocation: 'Use my location', wait: 'wait',
  },
  ta: {
    app: 'MadrasFlow', tagline: 'தென் சென்னை கூட்ட முன்னறிவிப்பு', simulated: 'உருவகப்படுத்தப்பட்ட தரவு',
    simulatedLong: 'இந்த எண்கள் ஒரு உருவகப்படுத்தலில் இருந்து வருகின்றன, நேரடி பயணிகள் எண்ணிக்கை அல்ல.',
    search: 'நிறுத்தம் அல்லது வழித்தடத்தைத் தேடுக', planTrip: 'பயணம் திட்டமிடு', favourites: 'சேமித்த நிறுத்தங்கள்', routes: 'வழித்தடங்கள்', nearby: 'அருகிலுள்ள நிறுத்தங்கள்',
    findNearby: 'என் அருகிலுள்ள நிறுத்தங்கள்', noFav: 'நிறுத்தத்தில் ☆ ஐ அழுத்திச் சேமிக்கவும்.', lastUpdated: 'இணைப்பு இல்லை · கடைசியாக புதுப்பித்தது',
    now: 'இப்போது', in30: '30 நிமி.', in60: '1 மணி', direction: 'திசை', nextVehicle: 'அடுத்து', min: 'நிமி',
    upcoming: 'அடுத்த புறப்பாடுகள்', waitOrGo: 'காத்திருக்கவா, போகவா?', from: 'இருந்து', to: 'வரை', departNow: 'இப்போது புறப்படு', departAt: 'புறப்படும் நேரம்',
    preferLow: 'குறைந்த கூட்டம் விரும்பு', preferLowHint: 'முதியோர், தனியாகப் பயணிக்கும் பெண்கள், சுமையுடன் பயணிப்போர்', go: 'வழிகளைக் காண்',
    fastest: 'விரைவானது', least_crowded: 'குறைந்த கூட்டம்', balanced: 'சமநிலை', alternative: 'மாற்று',
    transfers: 'மாற்றங்கள்', transfer: 'மாற்றம்', walk: 'நட', worst: 'அதிக கூட்டம்', arrive: 'வருகை', back: 'பின்',
    vehicle: 'வாகனம்', load: 'மதிப்பிட்ட சுமை', nextStops: 'அடுத்த நிறுத்தங்கள்', showMap: 'வரைபடம் காட்டு', hideMap: 'வரைபடம் மறை',
    depot: 'பணிமனை பலகை', depotShort: 'பணிமனை', commuter: 'பயணி', loading: 'ஏற்றுகிறது…', retry: 'மீண்டும்', noData: 'முன்னறிவிப்பு இன்னும் இல்லை — ஒவ்வொரு 5 நிமிடமும் இயங்கும்.',
    stale: 'கடந்த 10 நிமிடத்தில் நேரடி தரவு இல்லை', board: 'ஏறு', alight: 'இறங்கு', stops: 'நிறுத்தங்கள்', save: 'சேமி', saved: 'சேமிக்கப்பட்டது',
    LOW: 'குறைவு', MEDIUM: 'நடுத்தரம்', HIGH: 'அதிகம்', CROWDED: 'நெரிசல்', full: 'நிரம்பியது',
    currentLocation: 'தற்போதைய இடம்', locating: 'உங்கள் இடத்தைக் கண்டறிகிறது…', locationDenied: 'இடம் கிடைக்கவில்லை. நிறுத்தத்தைத் தேர்ந்தெடுக்கவும்.',
    near: 'அருகில்', minWalk: 'நிமி நடை', windowLabel: 'நேர இடைவெளி', widen: 'இடைவெளியை 15 நிமிடம் அதிகரி', narrow: 'இடைவெளியை 15 நிமிடம் குறை',
    rankBy: 'வரிசைப்படுத்து', rankCrowd: 'கூட்டம்', rankEta: 'வருகை நேரம்', rankCost: 'கட்டணம்', rankWalk: 'நடை', rankTransfers: 'மாற்றங்கள்',
    filters: 'வடிகட்டிகள்', apply: 'பயன்படுத்து', reset: 'மீட்டமை', modes: 'போக்குவரத்து வகை', bus: 'பேருந்து', mrts: 'எம்.ஆர்.டி.எஸ்', metro: 'மெட்ரோ',
    maxWalk: 'அதிகபட்ச நடை', any: 'ஏதேனும்', maxFare: 'அதிகபட்ச கட்டணம்', maxTransfers: 'மாற்றங்கள்', direct: 'நேரடி மட்டும்', upTo1: '1 வரை',
    accessibility: 'அணுகல்தன்மை', stepFree: 'படிகள் இல்லா நிலையங்கள்', stepFreeHint: 'மின்தூக்கி உள்ள நிலையங்கள்; தாழ்தளப் பேருந்து உறுதி இல்லை',
    women: 'பெண்கள் பயணம்', womenHint: 'சாதாரண MTC பேருந்துகளில் இலவசம்; இரவில் குறைந்த நடை, குறைந்த காத்திருப்பு',
    leave: 'புறப்பாடு', options: 'வழிகள்', noRoutesSlot: 'இந்த நேரத்தில் உங்கள் வடிகட்டிகளுக்குப் பொருந்தும் வழி இல்லை.', bestOverall: 'சிறந்த தேர்வு',
    free_bus_women: 'பெண்களுக்கு பேருந்து இலவசம்', low_floor: 'தாழ்தளப் பேருந்து உறுதி இல்லை', after_dark: 'இரவு: குறைந்த நடை, காத்திருப்பு',
    routeMap: 'வழி வரைபடம்', mapOffline: 'இணைப்பு இல்லாததால் வரைபடம் இல்லை. கீழே உள்ள படிகள் வேலை செய்யும்.', prevSlot: 'முந்தைய புறப்பாடு', nextSlot: 'அடுத்த புறப்பாடு',
    fare: 'கட்டணம்', updating: 'புதுப்பிக்கிறது…', pickStops: 'இரண்டு நிறுத்தங்களையும் பட்டியலில் இருந்து தேர்ந்தெடுக்கவும்', useStop: 'நிறுத்தத்தைத் தேர்ந்தெடு', useLocation: 'என் இடத்தைப் பயன்படுத்து', wait: 'காத்திருப்பு',
  },
} as const

export type Key = keyof typeof dict.en
export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: 'en', setLang: () => {} })
export function useT() {
  const { lang } = useContext(LangContext)
  return (k: Key) => dict[lang][k] ?? dict.en[k]
}
