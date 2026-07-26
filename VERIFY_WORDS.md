# Verify these — Sing Khmer predictions for words NOT in the database

These 96 common Khmer words are **not** in `data/vocabulary.csv`. Each row is
the engine's **single best guess** at how you'd type it in Sing Khmer, derived purely
from the pattern in your existing data (see `PATTERNS.md`).

On the words already in the DB, this predictor's top guess exactly matches a spelling
you actually typed **~46%** of the time — so expect roughly half the rows below to need a
fix. Please correct the wrong ones in the last column (and ✅ the right ones); I'll fold
the verified spellings back into the vocabulary.

| # | Khmer | predicted | ✅ / ✏️ correct spelling |
|--:|-------|-----------|--------------------------|
| 1 | បបរ | `bobo` | |
| 2 | គុយទាវ | `kuyoteav` | |
| 3 | សម្ល | `sormlo` | |
| 4 | អំបិល | `ombel` | |
| 5 | ស្ករ | `sko` | |
| 6 | ម្រេច | `mrech` | |
| 7 | ខ្ទឹម | `khteum` | |
| 8 | ម្ទេស | `mtes` | |
| 9 | ត្រសក់ | `trosork` | |
| 10 | ស្ពៃ | `spai` | |
| 11 | ការ៉ុត | `karut` | |
| 12 | ដំឡូង | `domlong` | |
| 13 | ពោត | `pout` | |
| 14 | សណ្ដែក | `sorndaek` | |
| 15 | ស៊ុត | `sot` | |
| 16 | ទឹកដោះគោ | `teukordosko` | |
| 17 | បៀរ | `bie` | |
| 18 | សត្វ | `sortvo` | |
| 19 | សេះ | `seh` | |
| 20 | ពពែ | `popea` | |
| 21 | ចៀម | `jiem` | |
| 22 | ដំរី | `domri` | |
| 23 | ខ្លា | `khla` | |
| 24 | សិង្ហ | `sengho` | |
| 25 | កង្កែប | `korngkeap` | |
| 26 | មូស | `mus` | |
| 27 | មេអំបៅ | `meombov` | |
| 28 | បង្កង | `bongkong` | |
| 29 | មេឃ | `mekh` | |
| 30 | ព្យុះ | `pyuh` | |
| 31 | ដី | `dey` | |
| 32 | ស្លឹក | `sleuk` | |
| 33 | ឫស្សី | `reussey` | |
| 34 | ដើមឈើ | `dermocher` | |
| 35 | ត្រចៀក | `trojiek` | |
| 36 | ច្រមុះ | `jromuh` | |
| 37 | អណ្ដាត | `ondat` | |
| 38 | ស្មា | `sma` | |
| 39 | ខ្នង | `khnong` | |
| 40 | ឆ្អឹង | `cheung` | |
| 41 | ឈាម | `cheam` | |
| 42 | ស្ត្រី | `strey` | |
| 43 | គ្រូពេទ្យ | `krupetyo` | |
| 44 | កសិករ | `korsekor` | |
| 45 | នាយក | `neayok` | |
| 46 | បង្អួច | `bonguoch` | |
| 47 | ដំបូល | `dombol` | |
| 48 | ជញ្ជាំង | `jonhjoamng` | |
| 49 | ចាន | `jan` | |
| 50 | ស្លាបព្រា | `slaboprea` | |
| 51 | កាំបិត | `kambet` | |
| 52 | ចង្កឹះ | `jongkeuh` | |
| 53 | ពែង | `peang` | |
| 54 | កន្សែង | `kornseang` | |
| 55 | ពេលវេលា | `pelovelea` | |
| 56 | សប្ដាហ៍ | `sorbdah` | |
| 57 | ស្ដាប់ | `sdap` | |
| 58 | ក្រោក | `kraok` | |
| 59 | ស្រាល | `sral` | |
| 60 | ទីក្រុង | `tikrong` | |
| 61 | សាលារៀន | `salearien` | |
| 62 | មន្ទីរពេទ្យ | `montiropetyo` | |
| 63 | វត្ត | `votto` | |
| 64 | ស្ថានីយ | `sthaniy` | |
| 65 | នំ | `num` | |
| 66 | ចេក | `jek` | |
| 67 | ម្នាស់ | `mneas` | |
| 68 | ឪឡឹក | `ovleuk` | |
| 69 | ត្រប់ | `trop` | |
| 70 | ល្ពៅ | `lpov` | |
| 71 | ខ្ទិះ | `khteh` | |
| 72 | ត្រយូង | `troyung` | |
| 73 | វែងឆ្ងាយ | `veangochngay` | |
| 74 | ព្រិល | `pril` | |
| 75 | ពពក | `popok` | |
| 76 | ពិភពលោក | `piphopolouk` | |
| 77 | អាកាស | `ahkas` | |
| 78 | ប៉ូលិស | `bolis` | |
| 79 | ទាហាន | `teahan` | |
| 80 | អ្នកលក់ | `nokorlok` | |
| 81 | មេធាវី | `metheavi` | |
| 82 | ចុងភៅ | `jongophov` | |
| 83 | អ្នកនិពន្ធ | `nokornipontho` | |
| 84 | វិមាន | `vimean` | |
| 85 | សួន | `suon` | |
| 86 | សណ្ឋាគារ | `sornthakea` | |
| 87 | បណ្ណាល័យ | `bonnaly` | |
| 88 | រសៀល | `rosiel` | |
| 89 | អតីតកាល | `oteytokal` | |
| 90 | អនាគត | `oneakot` | |
| 91 | ចម្លើយ | `jomlery` | |
| 92 | សំណួរ | `somnuo` | |
| 93 | ក្តីសង្ឃឹម | `kteysorngkheum` | |
| 94 | មិត្តភាព | `mittopheap` | |
| 95 | ចំណេះ | `jomneh` | |
| 96 | បទពិសោធ | `botopisaot` | |
