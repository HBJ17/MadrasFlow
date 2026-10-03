// English / Tamil labels for the UI chrome and crowd levels.
import { createContext, useContext } from 'react'

export type Lang = 'en' | 'ta'

const dict = {
  en: {
    app: 'Koottam', tagline: 'South Chennai crowd forecast', simulated: 'Simulated data',
    simulatedLong: 'Numbers come from a calibrated simulation, not live passenger counts.',
    search: 'Search a stop or route', planTrip: 'Plan a trip', favourites: 'Saved stops', routes: 'Routes', nearby: 'Nearby stops',
    findNearby: 'Find stops near me', noFav: 'Tap ☆ on a stop to save it here.', lastUpdated: 'Offline · last updated',
    now: 'Now', in30: 'In 30 min', in60: 'In 1 h', direction: 'Direction', nextVehicle: 'next', min: 'min',
    upcoming: 'Next departures', waitOrGo: 'Wait or go?', from: 'From', to: 'To', departNow: 'Leave now', departAt: 'Leave at',
    preferLow: 'Prefer less crowded', preferLowHint: 'For seniors, women travelling alone, people with luggage', go: 'Find routes',
    fastest: 'Fastest', least_crowded: 'Least crowded', balanced: 'Balanced', alternative: 'Alternative',
    transfers: 'transfers', transfer: 'transfer', walk: 'Walk', worst: 'Busiest', arrive: 'Arrive', back: 'Back',
    vehicle: 'Vehicle', load: 'Estimated load', nextStops: 'Next stops', showMap: 'Show map', hideMap: 'Hide map',
    depot: 'Depot dashboard', commuter: 'Commuter', loading: 'Loading…', retry: 'Retry', noData: 'No forecast yet — the forecast job runs every 5 minutes.',
    stale: 'No live data in the last 10 min', board: 'Board', alight: 'Get off', stops: 'stops', save: 'Save stop', saved: 'Saved',
    LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High', CROWDED: 'Crowded', full: 'full',
  },
  ta: {
    app: 'கூட்டம்', tagline: 'தென் சென்னை கூட்ட முன்னறிவிப்பு', simulated: 'உருவகப்படுத்தப்பட்ட தரவு',
    simulatedLong: 'இந்த எண்கள் ஒரு உருவகப்படுத்தலில் இருந்து வருகின்றன, நேரடி பயணிகள் எண்ணிக்கை அல்ல.',
    search: 'நிறுத்தம் அல்லது வழித்தடத்தைத் தேடுக', planTrip: 'பயணம் திட்டமிடு', favourites: 'சேமித்த நிறுத்தங்கள்', routes: 'வழித்தடங்கள்', nearby: 'அருகிலுள்ள நிறுத்தங்கள்',
    findNearby: 'என் அருகிலுள்ள நிறுத்தங்கள்', noFav: 'நிறுத்தத்தில் ☆ ஐ அழுத்திச் சேமிக்கவும்.', lastUpdated: 'இணைப்பு இல்லை · கடைசியாக புதுப்பித்தது',
    now: 'இப்போது', in30: '30 நிமி.', in60: '1 மணி', direction: 'திசை', nextVehicle: 'அடுத்து', min: 'நிமி',
    upcoming: 'அடுத்த புறப்பாடுகள்', waitOrGo: 'காத்திருக்கவா, போகவா?', from: 'இருந்து', to: 'வரை', departNow: 'இப்போது புறப்படு', departAt: 'புறப்படும் நேரம்',
    preferLow: 'குறைந்த கூட்டம் விரும்பு', preferLowHint: 'முதியோர், தனியாகப் பயணிக்கும் பெண்கள், சுமையுடன் பயணிப்போர்', go: 'வழிகளைக் காண்',
    fastest: 'விரைவானது', least_crowded: 'குறைந்த கூட்டம்', balanced: 'சமநிலை', alternative: 'மாற்று',
    transfers: 'மாற்றங்கள்', transfer: 'மாற்றம்', walk: 'நட', worst: 'அதிக கூட்டம்', arrive: 'வருகை', back: 'பின்',
    vehicle: 'வாகனம்', load: 'மதிப்பிட்ட சுமை', nextStops: 'அடுத்த நிறுத்தங்கள்', showMap: 'வரைபடம் காட்டு', hideMap: 'வரைபடம் மறை',
    depot: 'பணிமனை பலகை', commuter: 'பயணி', loading: 'ஏற்றுகிறது…', retry: 'மீண்டும்', noData: 'முன்னறிவிப்பு இன்னும் இல்லை — ஒவ்வொரு 5 நிமிடமும் இயங்கும்.',
    stale: 'கடந்த 10 நிமிடத்தில் நேரடி தரவு இல்லை', board: 'ஏறு', alight: 'இறங்கு', stops: 'நிறுத்தங்கள்', save: 'சேமி', saved: 'சேமிக்கப்பட்டது',
    LOW: 'குறைவு', MEDIUM: 'நடுத்தரம்', HIGH: 'அதிகம்', CROWDED: 'நெரிசல்', full: 'நிரம்பியது',
  },
} as const

export type Key = keyof typeof dict.en
export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: 'en', setLang: () => {} })
export function useT() {
  const { lang } = useContext(LangContext)
  return (k: Key) => dict[lang][k] ?? dict.en[k]
}
