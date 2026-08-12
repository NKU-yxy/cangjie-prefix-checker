main(): Unit {
    let values_5_772559: ArrayList<Int64> = ArrayList<Int64>(15)
    values_5_772559.add(11)
    values_5_772559.add(ArrayList<Int64>())
    values_5_772559.add(73, 0)

    let clone_5_772559: () -> ArrayList<Int64> = values_5_772559.clone
    let copied_5_772559: ArrayList<Int64> = clone_5_772559()
}
