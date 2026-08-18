import std.collection.*

func emptyMap(): HashMap<String, Int64> {
    HashMap<String, Int64>()
}

func mapSize(m: HashMap<String, Int64>): Int64 {
    m.size
}

func sampleKey(): String {
    "k"
}

func sampleVal(): Int64 {
    42
}

func tag(): String {
    "map-tag"
}

func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(a: Int64, b: Int64): Int64 {
    a + b
}

func padDelta(s: String): String {
    s
}

func padEpsilon(flag: Bool): Bool {
    flag
}

func padZeta(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func padEta(n: Int64): Int64 {
    if (n < 0) {
        0
    } else {
        n
    }
}

main(): Unit {
    let m: HashMap<String, Int64> = emptyMap()
    println("start=" + (mapSize(m)).toString())
    println("key=" + (sampleKey()).toString())
    println("val=" + (sampleVal()).toString())
    println(tag())
    println("pad=" + (padDelta(sampleKey())).toString())
    m.add(1, 2)
    println((m.size).toString())
}
