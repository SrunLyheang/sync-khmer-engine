# Verify these — Sing Khmer predictions for words NOT in the database

These 90 common Khmer words are **not** in `data/vocabulary.csv`. Each row is the
engine's **single best guess** at how you'd type it in Sing Khmer, from the pattern in your
existing data (see `PATTERNS.md`). Rules were refined from your first batch of corrections
(ិ→i, ឹ→er, ី→ey, ៀ→ea), and your 12 verified words are already folded into the DB.

Top-guess exact-match on the DB is now **~48%**, so expect some rows to need a fix. Correct
the wrong ones in the last column (✅ the right ones); I'll fold them in.

| # | Khmer | predicted | ✅ / ✏️ correct spelling |
|--:|-------|-----------|--------------------------|
| 1 | បបរ | `bobo` | |
| 2 | គុយទាវ | `kuyoteav` | |
| 3 | សម្ល | `sormlo` | |
| 4 | អំបិល | `ombil` | |
| 5 | ម្រេច | `mrech` | |
| 6 | ម្ទេស | `mtes` | |
| 7 | ត្រសក់ | `trosork` | |
| 8 | ស្ពៃ | `spai` | |
| 9 | ការ៉ុត | `karut` | |
| 10 | ដំឡូង | `domlong` | |
| 11 | ពោត | `pout` | |
| 12 | សណ្ដែក | `sorndaek` | |
| 13 | ស៊ុត | `sot` | |
| 14 | ទឹកដោះគោ | `terkordosko` | |
| 15 | បៀរ | `bea` | |
| 16 | សត្វ | `sortvo` | |
| 17 | សេះ | `seh` | |
| 18 | ពពែ | `popea` | |
| 19 | សិង្ហ | `singho` | |
| 20 | កង្កែប | `korngkeap` | |
| 21 | មូស | `mus` | |
| 22 | មេអំបៅ | `meombov` | |
| 23 | បង្កង | `bongkong` | |
| 24 | មេឃ | `mekh` | |
| 25 | ព្យុះ | `pyuh` | |
| 26 | ដី | `dey` | |
| 27 | ឫស្សី | `reussey` | |
| 28 | ដើមឈើ | `dermocher` | |
| 29 | ត្រចៀក | `trojeak` | |
| 30 | ច្រមុះ | `jromuh` | |
| 31 | អណ្ដាត | `ondat` | |
| 32 | ស្មា | `sma` | |
| 33 | ខ្នង | `khnong` | |
| 34 | ឆ្អឹង | `cherng` | |
| 35 | ឈាម | `cheam` | |
| 36 | ស្ត្រី | `strey` | |
| 37 | គ្រូពេទ្យ | `krupetyo` | |
| 38 | កសិករ | `korsikor` | |
| 39 | នាយក | `neayok` | |
| 40 | បង្អួច | `bonguoch` | |
| 41 | ដំបូល | `dombol` | |
| 42 | ជញ្ជាំង | `jonhjoamng` | |
| 43 | ចាន | `jan` | |
| 44 | ស្លាបព្រា | `slaboprea` | |
| 45 | កាំបិត | `kambit` | |
| 46 | ចង្កឹះ | `jongkerh` | |
| 47 | ពែង | `peang` | |
| 48 | កន្សែង | `kornseang` | |
| 49 | ពេលវេលា | `pelovelea` | |
| 50 | សប្ដាហ៍ | `sorbdah` | |
| 51 | ស្ដាប់ | `sdap` | |
| 52 | ក្រោក | `kraok` | |
| 53 | ស្រាល | `sral` | |
| 54 | ទីក្រុង | `tikrong` | |
| 55 | សាលារៀន | `salearean` | |
| 56 | មន្ទីរពេទ្យ | `monteyropetyo` | |
| 57 | វត្ត | `votto` | |
| 58 | ស្ថានីយ | `sthaneyy` | |
| 59 | នំ | `num` | |
| 60 | ចេក | `jek` | |
| 61 | ម្នាស់ | `mneas` | |
| 62 | ឪឡឹក | `ovlerk` | |
| 63 | ត្រប់ | `trop` | |
| 64 | ល្ពៅ | `lpov` | |
| 65 | ខ្ទិះ | `khtih` | |
| 66 | ត្រយូង | `troyung` | |
| 67 | វែងឆ្ងាយ | `veangochngay` | |
| 68 | ព្រិល | `pril` | |
| 69 | ពពក | `popok` | |
| 70 | ពិភពលោក | `piphopolouk` | |
| 71 | អាកាស | `ahkas` | |
| 72 | ប៉ូលិស | `bolis` | |
| 73 | ទាហាន | `teahan` | |
| 74 | អ្នកលក់ | `nokorlok` | |
| 75 | មេធាវី | `metheavey` | |
| 76 | ចុងភៅ | `jongophov` | |
| 77 | អ្នកនិពន្ធ | `nokornipontho` | |
| 78 | វិមាន | `vimean` | |
| 79 | សួន | `suon` | |
| 80 | សណ្ឋាគារ | `sornthakea` | |
| 81 | បណ្ណាល័យ | `bonnaly` | |
| 82 | រសៀល | `roseal` | |
| 83 | អតីតកាល | `oteytokal` | |
| 84 | អនាគត | `oneakot` | |
| 85 | ចម្លើយ | `jomlery` | |
| 86 | សំណួរ | `somnuo` | |
| 87 | ក្តីសង្ឃឹម | `kteysorngkherm` | |
| 88 | មិត្តភាព | `mittopheap` | |
| 89 | ចំណេះ | `jomneh` | |
| 90 | បទពិសោធ | `botopisaot` | |
